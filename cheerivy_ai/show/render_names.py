#!/usr/bin/env python3
"""
CHEERIVY Dynamic Name Template Voice Renderer
Renders dynamic player and AI template clips on-the-fly when new names are added.
"""

import os
import sys
import re
import json
import argparse
import subprocess
import tempfile
import soundfile as sf
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOW_DIR = SCRIPT_DIR
VOICE_REFS_DIR = os.path.join(SHOW_DIR, "voice_refs")
VOICE_BANK_DIR = os.path.join(SHOW_DIR, "voice_bank")
MANIFEST_PATH = os.path.join(VOICE_BANK_DIR, "manifest.json")

# Setup environment caches
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(SHOW_DIR)), ".cache")
os.environ["MPLCONFIGDIR"] = os.path.join(CACHE_DIR, "matplotlib")
os.environ["HF_HOME"] = os.path.join(CACHE_DIR, "huggingface")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

from render_bank import (
    TONE_CONFIG,
    clean_text,
    post_process_audio,
    render_line_with_pauses,
    get_all_script_lines
)


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s


def render_name_templates(name: str, say_like: str, is_ai: bool = False, force: bool = False):
    name_slug = slugify(name)
    print(f"[*] Rendering templates for '{name}' (say: '{say_like}', slug: '{name_slug}', AI: {is_ai})...")

    # Load F5-TTS
    from f5_tts.api import F5TTS
    f5 = F5TTS(device="mps")

    # Load ref texts
    ref_texts_file = os.path.join(VOICE_REFS_DIR, "ref_texts.json")
    if os.path.exists(ref_texts_file):
        with open(ref_texts_file) as f:
            ref_texts_map = json.load(f)
    else:
        ref_texts_map = {}

    # Load manifest
    manifest_data = {
        "version": 1,
        "sample_rate": 24000,
        "engine": "f5-tts 1.1.22",
        "rendered_at": datetime.now().isoformat(),
        "refs": {
            "calm": "voice_refs/ref_calm.wav",
            "build": "voice_refs/ref_build.wav",
            "erupt": "voice_refs/ref_erupt.wav",
            "whisper": "voice_refs/ref_whisper.wav"
        },
        "clips": []
    }
    existing_clips = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH) as f:
                manifest_data = json.load(f)
                for c in manifest_data.get("clips", []):
                    existing_clips[c["id"]] = c
        except Exception:
            pass

    all_lines = get_all_script_lines()
    template_lines = []

    for item in all_lines:
        cid = item["id"]
        raw_text = item["text"]
        has_p = "{p}" in raw_text
        has_ai = "{ai}" in raw_text

        if not has_p and not has_ai:
            continue

        if is_ai and not has_ai:
            continue
        if not is_ai and not has_p:
            continue

        template_lines.append(item)

    print(f"[*] Found {len(template_lines)} matching template lines.")

    for idx, item in enumerate(template_lines, 1):
        cid = item["id"]
        tone = item["tone"]
        raw_text = item["text"]
        max_dur = item["max"]
        clip_id = f"{cid}__{name_slug}"
        filename = f"{clip_id}.wav"
        final_abs_file = os.path.join(VOICE_BANK_DIR, tone, filename)
        final_rel_file = f"{tone}/{filename}"

        if not force and os.path.exists(final_abs_file) and clip_id in existing_clips:
            print(f"[{idx}/{len(template_lines)}] SKIP {clip_id}")
            continue

        if is_ai:
            t_text = raw_text.replace("{ai}", say_like)
            disp_text = raw_text.replace("{ai}", name)
        else:
            t_text = raw_text.replace("{p}", say_like)
            disp_text = raw_text.replace("{p}", name)

        clean_t = clean_text(t_text)
        print(f"[{idx}/{len(template_lines)}] RENDERING {clip_id} ({tone}) ... \"{clean_t}\"")

        tone_cfg = TONE_CONFIG.get(tone, TONE_CONFIG["calm"])
        ref_file_abs = os.path.join(VOICE_REFS_DIR, tone_cfg["ref_file"])
        ref_text = ref_texts_map.get(tone, "It's penalties. We go to the wire and beyond. Some can barely stand. Some are reduced to prayer.")

        temp_take = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        render_line_with_pauses(
            f5_engine=f5,
            ref_wav=ref_file_abs,
            ref_text=ref_text,
            full_raw_text=raw_text if (" / " in raw_text or " // " in raw_text) else clean_t,
            speed=tone_cfg["speed"],
            seed=1,
            final_take_path=temp_take
        )

        stats = post_process_audio(temp_take, final_abs_file, tone_cfg["lufs"])
        if os.path.exists(temp_take):
            os.remove(temp_take)

        clip_record = {
            "id": clip_id,
            "file": final_rel_file,
            "category": cid.split("_")[0],
            "tone": tone,
            "text": disp_text,
            "tts_text": clean_t,
            "template": True,
            "name": name,
            "duration_ms": stats["duration_ms"],
            "peak_offset_ms": stats["peak_offset_ms"],
            "lufs": stats["lufs"],
            "seed": 1,
            "asr_text": "",
            "wer": 0.0,
            "flags": []
        }

        existing_clips[clip_id] = clip_record
        manifest_data["clips"] = list(existing_clips.values())

        # Atomic manifest write
        tmp_m = MANIFEST_PATH + ".tmp"
        with open(tmp_m, "w") as f:
            json.dump(manifest_data, f, indent=2)
        os.replace(tmp_m, MANIFEST_PATH)

    print(f"[✓] Dynamic template rendering complete for '{name}'!")


def main():
    parser = argparse.ArgumentParser(description="Render dynamic name templates for CHEERIVY")
    parser.add_argument("--name", type=str, required=True, help="Display name of player/AI")
    parser.add_argument("--say-like", type=str, default=None, help="Phonetic text for TTS")
    parser.add_argument("--ai", action="store_true", help="Flag if this is an AI competitor name")
    parser.add_argument("--force", action="store_true", help="Force re-rendering")
    args = parser.parse_args()

    say_like = args.say_like if args.say_like else args.name
    render_name_templates(name=args.name, say_like=say_like, is_ai=args.ai, force=args.force)


if __name__ == "__main__":
    main()
