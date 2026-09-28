#!/usr/bin/env python3
"""
CHEERIVY Gap Tightener (tighten_gaps.py)
Re-applies Section 8 post-processing (trim, cap internal gaps, fades, loudness)
on existing clips in voice_bank/ in-place with a backup in voice_bank/_before_tighten/.
"""

import os
import sys
import shutil
import json
import glob
import subprocess
import tempfile
import numpy as np
import soundfile as sf
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOW_DIR = SCRIPT_DIR
VOICE_BANK_DIR = os.path.join(SHOW_DIR, "voice_bank")
BACKUP_DIR = os.path.join(VOICE_BANK_DIR, "_before_tighten")
MANIFEST_PATH = os.path.join(VOICE_BANK_DIR, "manifest.json")

# Tone caps from Section 8 step 2
GAP_CAPS = {
    "build": {"phrase": 120, "sentence": 180},
    "erupt": {"phrase": 120, "sentence": 180},
    "calm": {"phrase": 180, "sentence": 260},
    "whisper": {"phrase": 220, "sentence": 320},
}

TONE_LUFS = {
    "build": -18.0,
    "erupt": -15.0,
    "calm": -20.0,
    "whisper": -24.0,
}


def cap_internal_gaps(audio: np.ndarray, sr: int, max_gap_ms: int, threshold_db: float = -45.0, crossfade_ms: int = 10):
    thresh = 10.0 ** (threshold_db / 20.0)
    
    # Calculate smoothed energy envelope (5ms window) to avoid sample-level zero crossing jitter
    win_size = int(sr * 0.005)
    if win_size > 1 and len(audio) > win_size:
        env = np.convolve(np.abs(audio), np.ones(win_size)/win_size, mode="same")
    else:
        env = np.abs(audio)

    is_silent = env < thresh
    max_gap_samples = int(sr * (max_gap_ms / 1000.0))
    crossfade_samples = int(sr * (crossfade_ms / 1000.0))
    min_gap_samples = int(sr * 0.060)

    silent_runs = []
    in_s = False
    start = 0
    for i, s in enumerate(is_silent):
        if s and not in_s:
            in_s = True
            start = i
        elif not s and in_s:
            in_s = False
            silent_runs.append((start, i))
    if in_s:
        silent_runs.append((start, len(is_silent)))

    out_audio = audio.copy()
    gaps_cut = 0
    for start_idx, end_idx in reversed(silent_runs):
        gap_len = end_idx - start_idx
        if gap_len > max_gap_samples and gap_len >= min_gap_samples:
            excess = gap_len - max_gap_samples
            cut_start = start_idx + (gap_len - excess) // 2
            cut_end = cut_start + excess
            cf = min(crossfade_samples, cut_start, len(out_audio) - cut_end)
            if cf > 0:
                fade_out = np.linspace(1.0, 0.0, cf)
                fade_in = np.linspace(0.0, 1.0, cf)
                out_audio[cut_start-cf:cut_start] *= fade_out
                out_audio[cut_end:cut_end+cf] *= fade_in
            out_audio = np.concatenate([out_audio[:cut_start], out_audio[cut_end:]])
            gaps_cut += 1

    return out_audio, gaps_cut


def process_clip_file(wav_path: str, tone: str, target_sr: int = 24000):
    audio, sr = sf.read(wav_path)
    if audio.ndim > 1:
        audio = audio[:, 0]
    old_duration_ms = int(len(audio) / sr * 1000)

    # 1. Trim silence (10ms head, 30ms tail as per §8 step 1)
    thresh = 10.0 ** (-45.0 / 20.0)
    abs_audio = np.abs(audio)
    non_silent = np.where(abs_audio >= thresh)[0]
    if len(non_silent) > 0:
        head = int(sr * 0.010)
        tail = int(sr * 0.030)
        s_idx = max(0, non_silent[0] - head)
        e_idx = min(len(audio), non_silent[-1] + tail)
        audio = audio[s_idx:e_idx]

    if len(audio) == 0:
        audio = np.zeros(int(sr * 0.1), dtype=np.float32)

    # 2. Cap internal gaps
    caps = GAP_CAPS.get(tone, GAP_CAPS["calm"])
    audio, gaps_cut = cap_internal_gaps(audio, sr, max_gap_ms=caps["phrase"])

    # 3. Fades (5ms in, 20ms out)
    fade_in_len = min(int(sr * 0.005), len(audio) // 2)
    fade_out_len = min(int(sr * 0.020), len(audio) // 2)
    if fade_in_len > 0:
        audio[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
    if fade_out_len > 0:
        audio[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len)

    temp_trimmed = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    sf.write(temp_trimmed, audio, sr, subtype='PCM_16')

    # 4. Loudnorm
    target_lufs = TONE_LUFS.get(tone, -20.0)
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_trimmed,
        "-af", f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11",
        "-ar", str(target_sr),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_trimmed):
        os.remove(temp_trimmed)

    # 5. Measure
    norm_audio, norm_sr = sf.read(wav_path)
    if norm_audio.ndim > 1:
        norm_audio = norm_audio[:, 0]
    new_duration_ms = int(len(norm_audio) / norm_sr * 1000)

    win_len = int(norm_sr * 0.050)
    peak_offset_ms = 0
    if len(norm_audio) >= win_len:
        squared = norm_audio ** 2
        conv = np.convolve(squared, np.ones(win_len), mode='valid')
        peak_offset_ms = int(np.argmax(conv) / norm_sr * 1000)

    return {
        "old_ms": old_duration_ms,
        "new_ms": new_duration_ms,
        "gaps_cut": gaps_cut,
        "peak_offset_ms": peak_offset_ms,
        "lufs": target_lufs
    }


def main():
    print("[*] Starting gap tightening on voice_bank/ ...")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    manifest_data = {}
    clips_map = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH) as f:
                manifest_data = json.load(f)
                for c in manifest_data.get("clips", []):
                    clips_map[c["id"]] = c
        except Exception:
            pass

    # Find all wav files in calm, build, erupt, whisper, names
    all_wavs = []
    for tone in ["calm", "build", "erupt", "whisper"]:
        for p in glob.glob(os.path.join(VOICE_BANK_DIR, tone, "*.wav")):
            all_wavs.append((p, tone))
    for p in glob.glob(os.path.join(VOICE_BANK_DIR, "names", "*", "*.wav")):
        tone = os.path.splitext(os.path.basename(p))[0]
        all_wavs.append((p, tone))

    print(f"[*] Found {len(all_wavs)} clips to inspect and tighten.\n")
    print(f"{'ID / File':<35} | {'Old ms':<8} | {'New ms':<8} | {'Gaps Cut':<8}")
    print("-" * 68)

    for wav_path, tone in all_wavs:
        rel_path = os.path.relpath(wav_path, VOICE_BANK_DIR)
        clip_id = os.path.splitext(os.path.basename(wav_path))[0]
        
        # Backup
        backup_path = os.path.join(BACKUP_DIR, rel_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        if not os.path.exists(backup_path):
            shutil.copy2(wav_path, backup_path)

        res = process_clip_file(wav_path, tone)
        print(f"{rel_path:<35} | {res['old_ms']:<8} | {res['new_ms']:<8} | {res['gaps_cut']:<8}")

        # Update manifest record if exists
        if clip_id in clips_map:
            clips_map[clip_id]["duration_ms"] = res["new_ms"]
            clips_map[clip_id]["peak_offset_ms"] = res["peak_offset_ms"]
            clips_map[clip_id]["lufs"] = res["lufs"]

    if manifest_data:
        manifest_data["clips"] = list(clips_map.values())
        tmp_m = MANIFEST_PATH + ".tmp"
        with open(tmp_m, "w") as f:
            json.dump(manifest_data, f, indent=2)
        os.replace(tmp_m, MANIFEST_PATH)

    print("\n[✓] Gap tightening complete! Backups stored in voice_bank/_before_tighten/")


if __name__ == "__main__":
    main()
