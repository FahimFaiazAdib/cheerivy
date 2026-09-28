#!/usr/bin/env python3
"""
CHEERIVY Name Voice Renderer (render_name.py)
Renders 3 tone clips (calm, build, erupt) for a given player/AI name into voice_bank/names/<slug>/
according to Section 5.2 of VOICE_RENDER_SPEC.md.
"""

import os
import sys
import re
import json
import argparse
import subprocess
import tempfile
import numpy as np
import soundfile as sf
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOW_DIR = SCRIPT_DIR
VOICE_REFS_DIR = os.path.join(SHOW_DIR, "voice_refs")
VOICE_BANK_DIR = os.path.join(SHOW_DIR, "voice_bank")
NAMES_DIR = os.path.join(VOICE_BANK_DIR, "names")
INDEX_PATH = os.path.join(NAMES_DIR, "index.json")

# Setup environment caches
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(SHOW_DIR)), ".cache")
os.environ["MPLCONFIGDIR"] = os.path.join(CACHE_DIR, "matplotlib")
os.environ["HF_HOME"] = os.path.join(CACHE_DIR, "huggingface")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(NAMES_DIR, exist_ok=True)

TONE_SETTINGS = {
    "calm": {"speed": 0.95, "lufs": -20.0, "punct": ".", "ref_file": "ref_calm.wav"},
    "build": {"speed": 1.10, "lufs": -18.0, "punct": "!", "ref_file": "ref_build.wav"},
    "erupt": {"speed": 1.05, "lufs": -15.0, "punct": "!", "ref_file": "ref_erupt.wav"},
}


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s


def clean_name_text(text: str, punct: str = ".") -> str:
    """Apply text cleaning for name clips according to Section 3.1"""
    text = text.replace(":", ".").replace(";", ".").replace("—", ".").replace("–", ".")
    text = text.replace("...", ".").replace("…", ".")
    for ch in ['"', '“', '”', '(', ')', '[', ']', '*', '_']:
        text = text.replace(ch, "")
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.rstrip(".!?")
    return text + punct


def post_process_name_audio(input_wav: str, output_wav: str, target_lufs: float, target_sr: int = 24000) -> dict:
    audio, sr = sf.read(input_wav)
    if audio.ndim > 1:
        audio = audio[:, 0]

    # 1. Trim silence (-45 dBFS, keep 10ms head, 30ms tail as per §8 step 1)
    threshold_amp = 10.0 ** (-45.0 / 20.0)
    abs_audio = np.abs(audio)
    non_silent = np.where(abs_audio >= threshold_amp)[0]
    if len(non_silent) > 0:
        head_samples = int(sr * 0.010)
        tail_samples = int(sr * 0.030)
        start_idx = max(0, non_silent[0] - head_samples)
        end_idx = min(len(audio), non_silent[-1] + tail_samples)
        audio = audio[start_idx:end_idx]

    if len(audio) == 0:
        audio = np.zeros(int(sr * 0.1), dtype=np.float32)

    # 2. Fades (5ms in, 20ms out)
    fade_in_len = min(int(sr * 0.005), len(audio) // 2)
    fade_out_len = min(int(sr * 0.020), len(audio) // 2)
    if fade_in_len > 0:
        audio[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
    if fade_out_len > 0:
        audio[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len)

    temp_trimmed = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    sf.write(temp_trimmed, audio, sr, subtype='PCM_16')

    # 3. Loudnorm
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_trimmed,
        "-af", f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11",
        "-ar", str(target_sr),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_trimmed):
        os.remove(temp_trimmed)

    norm_audio, norm_sr = sf.read(output_wav)
    duration_ms = int(len(norm_audio) / norm_sr * 1000)
    return {"duration_ms": duration_ms, "lufs": target_lufs}


def render_single_name(name: str, say_like: str = None, f5_engine = None) -> str:
    name_slug = slugify(name)
    say_text = say_like if say_like else name
    target_dir = os.path.join(NAMES_DIR, name_slug)
    os.makedirs(target_dir, exist_ok=True)

    if f5_engine is None:
        from f5_tts.api import F5TTS
        f5_engine = F5TTS(device="mps")

    # Load ref texts
    ref_texts_file = os.path.join(VOICE_REFS_DIR, "ref_texts.json")
    if os.path.exists(ref_texts_file):
        with open(ref_texts_file) as f:
            ref_texts_map = json.load(f)
    else:
        ref_texts_map = {}

    rendered_files = {}

    for tone in ["calm", "build", "erupt"]:
        cfg = TONE_SETTINGS[tone]
        tts_text = clean_name_text(say_text, cfg["punct"])
        out_file = os.path.join(target_dir, f"{tone}.wav")
        rel_file = f"names/{name_slug}/{tone}.wav"

        ref_file = os.path.join(VOICE_REFS_DIR, cfg["ref_file"])
        ref_text = ref_texts_map.get(tone, "It's penalties. We go to the wire and beyond. Some can barely stand. Some are reduced to prayer.")

        temp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        f5_engine.infer(
            ref_file=ref_file,
            ref_text=ref_text,
            gen_text=tts_text,
            speed=cfg["speed"],
            seed=1,
            file_wave=temp_out,
            show_info=lambda *args: None
        )

        post_process_name_audio(temp_out, out_file, cfg["lufs"])
        if os.path.exists(temp_out):
            os.remove(temp_out)

        rendered_files[tone] = rel_file

    # Update names/index.json atomically
    index_data = {}
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH) as f:
                index_data = json.load(f)
        except Exception:
            index_data = {}

    index_data[name_slug] = {
        "slug": name_slug,
        "name": name,
        "say_like": say_text,
        "files": rendered_files,
        "updated_at": datetime.now().isoformat()
    }

    tmp_idx = INDEX_PATH + ".tmp"
    with open(tmp_idx, "w") as f:
        json.dump(index_data, f, indent=2)
    os.replace(tmp_idx, INDEX_PATH)

    print(f"READY {name_slug}")
    return name_slug


def main():
    parser = argparse.ArgumentParser(description="Render a single name in 3 tones (calm, build, erupt)")
    parser.add_argument("--name", type=str, required=True, help="Typed name (e.g. 'Rafi')")
    parser.add_argument("--say-like", type=str, default=None, help="Phonetic text (e.g. 'Rah-fee')")
    args = parser.parse_args()

    render_single_name(name=args.name, say_like=args.say_like)


if __name__ == "__main__":
    main()
