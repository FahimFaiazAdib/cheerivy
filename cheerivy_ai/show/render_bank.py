#!/usr/bin/env python3
"""
CHEERIVY Voice Bank Renderer (render_bank.py)
Generates the static voice bank clips, fallback names, and team names according to VOICE_RENDER_SPEC.md.
"""

import os
import sys
import re
import json
import csv
import time
import hashlib
import argparse
import subprocess
import tempfile
import numpy as np
import soundfile as sf
from datetime import datetime

# Workspace & cache paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOW_DIR = SCRIPT_DIR
VOICE_REFS_DIR = os.path.join(SHOW_DIR, "voice_refs")
VOICE_BANK_DIR = os.path.join(SHOW_DIR, "voice_bank")
NAMES_DIR = os.path.join(VOICE_BANK_DIR, "names")

# Setup environment caches
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(SHOW_DIR)), ".cache")
os.environ["MPLCONFIGDIR"] = os.path.join(CACHE_DIR, "matplotlib")
os.environ["HF_HOME"] = os.path.join(CACHE_DIR, "huggingface")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
os.makedirs(NAMES_DIR, exist_ok=True)

from render_name import render_single_name

# Tone render configurations (Section 6)
TONE_CONFIG = {
    "calm": {"speed": 0.95, "lufs": -20.0, "ref_file": "ref_calm.wav"},
    "build": {"speed": 1.10, "lufs": -18.0, "ref_file": "ref_build.wav"},
    "erupt": {"speed": 1.05, "lufs": -15.0, "ref_file": "ref_erupt.wav"},
    "whisper": {"speed": 0.90, "lufs": -24.0, "ref_file": "ref_whisper.wav"},
}

# Fallback and Team names to pre-render (Section 5.1)
FALLBACK_NAMES = [
    {"name": "Player one", "say": "Player one", "slug": "player-one"},
    {"name": "Player two", "say": "Player two", "slug": "player-two"},
    {"name": "The challenger", "say": "The challenger", "slug": "the-challenger"},
    {"name": "The machine", "say": "The machine", "slug": "the-machine"},
]

TEAM_NAMES = [
    {"name": "Fahim", "say": "Fahim", "slug": "fahim"},
    {"name": "Adib", "say": "Ah-deeb", "slug": "adib"},
    {"name": "Tahmid", "say": "Tah-mid", "slug": "tahmid"},
    {"name": "Atik", "say": "Ah-tik", "slug": "atik"},
    {"name": "CHEERIVY AI", "say": "Cheer-ivy, A I", "slug": "cheerivy-ai"},
]

# Tone caps from Section 8 step 2
GAP_CAPS = {
    "build": {"phrase": 120, "sentence": 180},
    "erupt": {"phrase": 120, "sentence": 180},
    "calm": {"phrase": 180, "sentence": 260},
    "whisper": {"phrase": 220, "sentence": 320},
}


def clean_text(text: str) -> str:
    """Apply cleaning rules specified in Section 3.1 of VOICE_RENDER_SPEC.md"""
    # Replace phrase and sentence breaks
    text = text.replace(" // ", ". ").replace(" / ", ". ")

    # Replace broken punctuation
    text = text.replace(":", ".")
    text = text.replace(";", ".")
    text = text.replace("—", ".")
    text = text.replace("–", ".")
    text = text.replace("...", ".")
    text = text.replace("…", ".")

    # Remove unwanted marks
    for ch in ['"', '“', '”', '(', ')', '[', ']', '*', '_']:
        text = text.replace(ch, "")

    # Collapse multiple punctuation
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'!{2,}', '!', text)
    text = re.sub(r'\?{2,}', '?', text)
    text = re.sub(r'\?!|\!\?', '!', text)

    # Lower-case ALL CAPS words (e.g. CHEERIVY -> Cheerivy), keeping "A I" or single letters
    words = text.split()
    cleaned_words = []
    for w in words:
        if w in ["AI", "AI.", "AI!", "AI,"]:
            cleaned_words.append(w.replace("AI", "A I"))
        elif w.isupper() and len(re.sub(r'[^A-Za-z]', '', w)) > 1:
            cleaned_words.append(w.capitalize())
        else:
            cleaned_words.append(w)
    text = " ".join(cleaned_words)

    # Replace multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()

    # Ensure proper sentence capitalization after . ! ?
    sentences = re.split(r'([.!?]\s+)', text)
    capitalized_parts = []
    for s in sentences:
        if s and not re.match(r'^[.!?]\s+$', s):
            s = s.strip()
            if s:
                s = s[0].upper() + s[1:]
        capitalized_parts.append(s)
    text = "".join(capitalized_parts).strip()

    # Ensure final punctuation
    if text and text[-1] not in ['.', '!', '?']:
        text += '.'

    return text


def compute_clip_hash(tts_text: str, tone: str, ref_file: str) -> str:
    data = f"{tts_text}|{tone}|{ref_file}".encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def word_error_rate(reference: str, hypothesis: str) -> float:
    def tokenize(s):
        s = re.sub(r'[^a-zA-Z0-9\s]', '', s.lower())
        return s.split()

    r = tokenize(reference)
    h = tokenize(hypothesis)
    if not r:
        return 0.0 if not h else 1.0

    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j

    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            if r[i - 1] == h[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = min(
                    d[i - 1][j] + 1,
                    d[i][j - 1] + 1,
                    d[i - 1][j - 1] + 1
                )
    return float(d[len(r)][len(h)]) / float(len(r))


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


def post_process_audio(input_wav_path: str, output_wav_path: str, tone: str, target_sr: int = 24000) -> dict:
    audio, sr = sf.read(input_wav_path)
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

    # 2. Cap internal gaps (Section 8 step 2)
    caps = GAP_CAPS.get(tone, GAP_CAPS["calm"])
    audio, gaps_cut = cap_internal_gaps(audio, sr, max_gap_ms=caps["phrase"])

    # 3. Apply Fades (5ms in, 20ms out)
    fade_in_len = min(int(sr * 0.005), len(audio) // 2)
    fade_out_len = min(int(sr * 0.020), len(audio) // 2)
    
    if fade_in_len > 0:
        audio[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
    if fade_out_len > 0:
        audio[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len)

    temp_trimmed = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    sf.write(temp_trimmed, audio, sr, subtype='PCM_16')

    # 4. Loudnorm normalisation
    target_lufs = TONE_CONFIG.get(tone, TONE_CONFIG["calm"])["lufs"]
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_trimmed,
        "-af", f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11",
        "-ar", str(target_sr),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        output_wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_trimmed):
        os.remove(temp_trimmed)

    # 5. Measure stats
    norm_audio, norm_sr = sf.read(output_wav_path)
    if norm_audio.ndim > 1:
        norm_audio = norm_audio[:, 0]
    duration_ms = int(len(norm_audio) / norm_sr * 1000)

    win_len = int(norm_sr * 0.050)
    peak_offset_ms = 0
    if len(norm_audio) >= win_len:
        squared = norm_audio ** 2
        conv = np.convolve(squared, np.ones(win_len), mode='valid')
        peak_offset_ms = int(np.argmax(conv) / norm_sr * 1000)

    return {
        "duration_ms": duration_ms,
        "peak_offset_ms": peak_offset_ms,
        "lufs": target_lufs,
        "gaps_cut": gaps_cut
    }


def render_line(f5_engine, ref_wav: str, ref_text: str, full_raw_text: str, speed: float, seed: int, final_take_path: str):
    """
    Section 4 Rule 5: One model call per line.
    Never split a line into several calls and never join parts with inserted silence.
    Phrase breaks / and // are sent as '. ' in the same model call.
    """
    text_for_tts = clean_text(full_raw_text)
    f5_engine.infer(
        ref_file=ref_wav,
        ref_text=ref_text,
        gen_text=text_for_tts,
        speed=speed,
        seed=seed,
        file_wave=final_take_path,
        show_info=lambda *args: None
    )


def get_all_spec_lines():
    """Extract and compile all lines defined in Section 10 of updated VOICE_RENDER_SPEC.md"""
    lines = []

    # 10.1 Kick-off
    lines.extend([
        {"id": "kick_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 9.0, "text": "Under the lights of a laboratory in Palashi. / One human being. / One machine. // Sixty centimetres of destiny between them."},
        {"id": "kick_ai_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "They say the machine cannot be beaten. // Tonight, someone has come to ask it a question."},
        {"id": "kick_ai_03", "mode": "ai", "tone": "calm", "name_before": None, "max": 9.0, "text": "Three minutes. / One ball. / And a question as old as invention itself. // Can we defeat what we have made?"},
        {"id": "kick_ai_04", "mode": "ai", "tone": "calm", "name_before": "calm", "max": 4.0, "text": "Across the table. / Eight megahertz of cold intent."},
        {"id": "kick_pvp_01", "mode": "pvp", "tone": "calm", "name_before": None, "max": 9.0, "text": "Two players. / One ball. / Three minutes. // Friends before kick-off. / Rivals until the whistle."},
        {"id": "kick_pvp_02", "mode": "pvp", "tone": "calm", "name_before": None, "max": 7.0, "text": "Under the lights of a laboratory in Palashi. / Two challengers. // Only one will walk away smiling."},
        {"id": "kick_pvp_03", "mode": "pvp", "tone": "calm", "name_before": None, "max": 6.0, "text": "No machines tonight. / Just nerve, and hands, and hope."},
        {"id": "kick_intro", "mode": "all", "tone": "calm", "name_before": "calm", "max": 3.0, "text": "Flesh, and nerve, and hope."},
        {"id": "kick_versus", "mode": "all", "tone": "calm", "name_before": None, "max": 1.0, "text": "Versus."},
        {"id": "kick_04", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "The whistle is close. / The lab holds its breath."},
        {"id": "kick_05", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.8, "text": "And we are underway!"},
        {"id": "kick_06", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.2, "text": "Here we go!"},
    ])

    # 10.2 Build-ups
    lines.extend([
        {"id": "bld_01", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Now then!"},
        {"id": "bld_02", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Off the wall!"},
        {"id": "bld_03", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Still alive!"},
        {"id": "bld_04", "mode": "all", "tone": "build", "name_before": None, "max": 1.0, "text": "Oh, this is dangerous!"},
        {"id": "bld_05", "mode": "all", "tone": "build", "name_before": None, "max": 1.0, "text": "Is there a way through?"},
        {"id": "bld_06", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Here it comes!"},
        {"id": "bld_07", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Straight at it!"},
        {"id": "bld_08", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Oh, here we go!"},
        {"id": "bld_09", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Look at this!"},
        {"id": "bld_10", "mode": "all", "tone": "build", "name_before": None, "max": 1.0, "text": "Here comes the reply!"},
        {"id": "bld_again", "mode": "all", "tone": "build", "name_before": "build", "max": 0.6, "text": "Again!"},
        {"id": "bld_ai_01", "mode": "ai", "tone": "build", "name_before": None, "max": 1.0, "text": "The machine is moving!"},
        {"id": "bld_ai_02", "mode": "ai", "tone": "build", "name_before": None, "max": 1.0, "text": "The machine strikes back!"},
        {"id": "bld_ai_03", "mode": "ai", "tone": "build", "name_before": None, "max": 0.7, "text": "Incoming!"},
        {"id": "bld_pvp_01", "mode": "pvp", "tone": "build", "name_before": None, "max": 1.0, "text": "Straight back at them!"},
    ])

    # 10.3 Goal payoffs
    lines.extend([
        {"id": "pay_g_01", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 1.5, "text": "Oh, it's in!"},
        {"id": "pay_g_02", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.5, "text": "Goal! Goal!"},
        {"id": "pay_g_03", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 1.2, "text": "It's there!"},
        {"id": "pay_g_04", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 1.8, "text": "Oh, what a strike!"},
        {"id": "pay_g_05", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.3, "text": "Magnificent!"},
        {"id": "pay_g_06", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.3, "text": "Oh, you beauty!"},
        {"id": "pay_g_07", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.8, "text": "Through! It's through!"},
        {"id": "pay_g_08", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 0.9, "text": "Scores!"},
        {"id": "pay_gh_ai", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.0, "text": "The machine is beaten!"},
        {"id": "pay_ga_01", "mode": "ai", "tone": "build", "name_before": None, "max": 1.8, "text": "And the machine scores."},
        {"id": "pay_ga_02", "mode": "ai", "tone": "build", "name_before": None, "max": 2.5, "text": "Oh, cruel. / Cruel mathematics."},
        {"id": "pay_ga_03", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.2, "text": "It's in! The machine strikes!"},
        {"id": "pay_ga_04", "mode": "ai", "tone": "build", "name_before": None, "max": 2.0, "text": "Through, and past, and in."},
    ])

    # 10.4 Goal tails
    lines.extend([
        {"id": "tail_g_01", "mode": "all", "tone": "calm", "name_before": None, "max": 3.0, "text": "Poetry, in a plywood arena."},
        {"id": "tail_g_02", "mode": "all", "tone": "calm", "name_before": None, "max": 4.0, "text": "Mark it down. / Remember where you were."},
        {"id": "tail_g_03", "mode": "all", "tone": "calm", "name_before": None, "max": 5.0, "text": "Written in the stars. / And now, in the scoresheet."},
        {"id": "tail_g_04", "mode": "all", "tone": "calm", "name_before": None, "max": 3.0, "text": "Nothing anyone could do about that."},
        {"id": "tail_g_05", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "Clinical. / Absolutely clinical."},
        {"id": "tail_gh_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 5.0, "text": "The silicon did the maths. / The human did the magic."},
        {"id": "tail_gh_ai_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.0, "text": "Somewhere, a transistor weeps."},
        {"id": "tail_gh_ai_03", "mode": "ai", "tone": "build", "name_before": None, "max": 3.5, "text": "The machine calculated everything, except that!"},
        {"id": "tail_gh_ai_04", "mode": "ai", "tone": "build", "name_before": None, "max": 3.5, "text": "For every student who ever lost to a computer!"},
        {"id": "tail_gh_ai_05", "mode": "ai", "tone": "build", "name_before": "build", "max": 3.5, "text": "Has found a flaw in the code!"},
        {"id": "tail_ga_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.5, "text": "Cold. / Calculated. / Clinical."},
        {"id": "tail_ga_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 4.5, "text": "The machine does not celebrate. / It does not need to."},
        {"id": "tail_ga_03", "mode": "ai", "tone": "calm", "name_before": None, "max": 4.0, "text": "It saw that before anyone in this room had thought it."},
        {"id": "tail_ga_04", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.0, "text": "Eight megahertz. / No mercy."},
        {"id": "tail_ga_05", "mode": "ai", "tone": "calm", "name_before": None, "max": 4.0, "text": "One line of code, / and one more goal."},
        {"id": "tail_pvp_01", "mode": "pvp", "tone": "calm", "name_before": None, "max": 2.5, "text": "Friendship is on hold."},
        {"id": "tail_pvp_02", "mode": "pvp", "tone": "calm", "name_before": None, "max": 4.0, "text": "That one will be talked about in the canteen."},
        {"id": "tail_pvp_03", "mode": "pvp", "tone": "calm", "name_before": None, "max": 4.0, "text": "Bragging rights. / And they are being collected."},
        {"id": "tail_pvp_04", "mode": "pvp", "tone": "build", "name_before": None, "max": 3.0, "text": "Whoever said this was a friendly?"},
    ])

    # 10.5 Saves
    lines.extend([
        {"id": "pay_sv_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.0, "text": "Denied!"},
        {"id": "pay_sv_02", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.0, "text": "Saved!"},
        {"id": "pay_sv_03", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.0, "text": "Not today!"},
        {"id": "pay_sv_04", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.4, "text": "Oh, what a stop!"},
        {"id": "pay_sv_05", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.0, "text": "Blocked!"},
        {"id": "tail_sv_01", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "Moved before the shot was even struck."},
        {"id": "tail_sv_02", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "Read it all the way."},
        {"id": "tail_sv_03", "mode": "all", "tone": "build", "name_before": None, "max": 2.0, "text": "Reflexes like lightning!"},
        {"id": "tail_sv_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.0, "text": "The machine stands in the doorway."},
        {"id": "tail_sv_ai_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 4.0, "text": "Read like a textbook. / One it wrote itself."},
        {"id": "tail_sv_ai_03", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.0, "text": "Not today, says the silicon."},
    ])

    # 10.6 Near miss
    lines.extend([
        {"id": "pay_nm_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.3, "text": "Ohhh! Inches!"},
        {"id": "pay_nm_02", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.2, "text": "Oh, so close!"},
        {"id": "pay_nm_03", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.8, "text": "Wide! Agonisingly wide!"},
        {"id": "tail_nm_01", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "It kissed the line, / and ran away."},
        {"id": "tail_nm_02", "mode": "all", "tone": "calm", "name_before": None, "max": 4.0, "text": "Mere inches. / A whole lifetime of inches."},
        {"id": "tail_nm_03", "mode": "all", "tone": "calm", "name_before": "calm", "max": 2.5, "text": "Agony. / Pure agony."},
    ])

    # 10.7 Wall bounce and fast shots
    lines.extend([
        {"id": "wall_01", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "Off the wall! Geometry itself has joined the game!"},
        {"id": "wall_02", "mode": "all", "tone": "build", "name_before": None, "max": 2.0, "text": "Bank shot! Pure trigonometry!"},
        {"id": "wall_03", "mode": "all", "tone": "build", "name_before": None, "max": 2.0, "text": "Off the side, and still alive!"},
        {"id": "fast_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 2.5, "text": "That left the flipper like a monsoon wind!"},
        {"id": "fast_02", "mode": "all", "tone": "build", "name_before": None, "max": 2.0, "text": "The camera barely believed it!"},
        {"id": "fast_03", "mode": "all", "tone": "build", "name_before": None, "max": 1.0, "text": "A rocket!"},
    ])
    speed_words = {
        60: "Sixty", 70: "Seventy", 80: "Eighty",
        90: "Ninety", 100: "One hundred", 110: "One hundred and ten",
        120: "One hundred and twenty", 130: "One hundred and thirty",
        140: "One hundred and forty", 150: "One hundred and fifty"
    }
    for spd_val, word in speed_words.items():
        lines.append({
            "id": f"spd_{spd_val:03d}",
            "mode": "all",
            "tone": "build",
            "name_before": None,
            "max": 2.5,
            "text": f"{word} centimetres a second!"
        })

    # 10.8 Rally, lull colour, chaos
    lines.extend([
        {"id": "rally_05", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "Five touches. / Neither will blink."},
        {"id": "rally_08", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "Eight! This rally has a heartbeat of its own!"},
        {"id": "rally_12", "mode": "all", "tone": "erupt", "name_before": None, "max": 3.5, "text": "Twelve! Twelve touches! Somebody has to break!"},
        {"id": "rally_gen", "mode": "all", "tone": "build", "name_before": None, "max": 2.5, "text": "Back, and forth, and back again."},
        {"id": "col_01", "mode": "all", "tone": "calm", "name_before": None, "max": 4.0, "text": "The ball rests. / The minds do not."},
        {"id": "col_02", "mode": "all", "tone": "calm", "name_before": None, "max": 2.0, "text": "A moment to breathe."},
        {"id": "col_03", "mode": "all", "tone": "calm", "name_before": None, "max": 3.0, "text": "The lab is quiet. / Too quiet."},
        {"id": "col_04", "mode": "all", "tone": "calm", "name_before": None, "max": 5.0, "text": "A hand on a joystick. / A heartbeat in the fingertips."},
        {"id": "col_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 4.0, "text": "Somewhere in that chip, a decision is being made."},
        {"id": "col_ai_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.5, "text": "Thirty-two kilobytes of ambition, waiting."},
        {"id": "col_pvp_01", "mode": "pvp", "tone": "calm", "name_before": None, "max": 3.5, "text": "Two minds, / one ball, / no mercy."},
        {"id": "lost_01", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "Where is it? / Even the camera has lost it!"},
        {"id": "lost_02", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "The ball has gone into hiding."},
        {"id": "blind_01", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.0, "text": "The machine has lost its eyes!"},
        {"id": "blind_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.0, "text": "It plays now, on memory alone."},
        {"id": "sight_01", "mode": "ai", "tone": "build", "name_before": None, "max": 2.5, "text": "And the machine can see again."},
        {"id": "frz_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 2.5, "text": "Frozen! / Not a single step!"},
        {"id": "frz_02", "mode": "all", "tone": "build", "name_before": None, "max": 1.5, "text": "Ice in the circuits!"},
        {"id": "frz_03", "mode": "all", "tone": "build", "name_before": None, "max": 2.5, "text": "Three seconds. / Use them!"},
        {"id": "frz_ai", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.5, "text": "The machine cannot move!"},
    ])

    # 10.9 Match memory callbacks
    lines.extend([
        {"id": "cb_sv3", "mode": "all", "tone": "build", "name_before": None, "max": 4.0, "text": "Three shots. / Three times the door has held."},
        {"id": "cb_sv5", "mode": "all", "tone": "build", "name_before": None, "max": 4.0, "text": "Five saves now. / Is anyone getting past?"},
        {"id": "cb_break", "mode": "all", "tone": "erupt", "name_before": None, "max": 1.8, "text": "And now it breaks!"},
        {"id": "cb_reply", "mode": "all", "tone": "erupt", "name_before": None, "max": 3.0, "text": "The reply! / Instant! / Defiant!"},
        {"id": "cb_again", "mode": "all", "tone": "build", "name_before": None, "max": 3.5, "text": "Denied from there before. / Not this time!"},
    ])

    # 10.10 Score situations
    lines.extend([
        {"id": "sit_open", "mode": "all", "tone": "build", "name_before": "build", "max": 1.2, "text": "First blood!"},
        {"id": "sit_open_h_ai", "mode": "ai", "tone": "build", "name_before": None, "max": 2.0, "text": "First blood to humanity!"},
        {"id": "sit_open_a_ai", "mode": "ai", "tone": "calm", "name_before": None, "max": 2.0, "text": "The machine draws first."},
        {"id": "sit_equal_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 4.0, "text": "Level! / Everything we thought we knew, is gone!"},
        {"id": "sit_equal_02", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "All square! / We start again!"},
        {"id": "sit_lead", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 1.5, "text": "Into the lead!"},
        {"id": "sit_lead_h_ai", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.0, "text": "Humanity is in front!"},
        {"id": "sit_lead_a_ai", "mode": "ai", "tone": "build", "name_before": None, "max": 2.2, "text": "The machine edges ahead."},
        {"id": "sit_extend", "mode": "all", "tone": "calm", "name_before": None, "max": 4.0, "text": "The grip tightens. / Slowly. / Surely."},
        {"id": "sit_comeback", "mode": "all", "tone": "erupt", "name_before": None, "max": 5.5, "text": "From two behind! / This is not a match anymore. / This is a story."},
        {"id": "sit_rout", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "This is becoming a lesson."},
        {"id": "sit_rout_h_ai", "mode": "ai", "tone": "erupt", "name_before": None, "max": 2.2, "text": "The machine is in pieces!"},
    ])

    # 10.11 Scorelines (Leader First: h >= a for 0..5 -> 21 clips)
    digits_word = {0: "Nil", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
    for h in range(6):
        for a in range(h + 1):
            if h == a and h != 0:
                sc_text = f"{digits_word[h]} all."
            elif h == 0 and a == 0:
                sc_text = "Nil, nil."
            else:
                sc_text = f"{digits_word[h]}, {digits_word[a].lower()}."
            lines.append({
                "id": f"sc_{h}_{a}",
                "mode": "all",
                "tone": "calm",
                "name_before": "calm",
                "max": 2.0,
                "text": sc_text
            })

    # 10.12 Clock
    lines.extend([
        {"id": "clk_60", "mode": "all", "tone": "build", "name_before": None, "max": 3.0, "text": "One minute. / Sixty heartbeats."},
        {"id": "clk_30a", "mode": "all", "tone": "build", "name_before": None, "max": 4.0, "text": "Thirty seconds, / and the clock belongs to no one."},
        {"id": "clk_30b", "mode": "all", "tone": "build", "name_before": None, "max": 4.5, "text": "Thirty seconds. / Is there time? / Is there belief?"},
        {"id": "cd_10", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Ten!"},
        {"id": "cd_09", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Nine!"},
        {"id": "cd_08", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Eight!"},
        {"id": "cd_07", "mode": "all", "tone": "build", "name_before": None, "max": 0.8, "text": "Seven!"},
        {"id": "cd_06", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "Six!"},
        {"id": "cd_05", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "Five!"},
        {"id": "cd_04", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "Four!"},
        {"id": "cd_03", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "Three!"},
        {"id": "cd_02", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "Two!"},
        {"id": "cd_01", "mode": "all", "tone": "erupt", "name_before": None, "max": 0.8, "text": "One!"},
        {"id": "clk_last", "mode": "all", "tone": "erupt", "name_before": "erupt", "max": 3.0, "text": "At the death! / At the very death!"},
        {"id": "clk_whistle", "mode": "all", "tone": "erupt", "name_before": None, "max": 2.0, "text": "And there is the whistle!"},
    ])

    # 10.13 Full time
    lines.extend([
        {"id": "ft_over", "mode": "all", "tone": "calm", "name_before": None, "max": 1.5, "text": "It is over."},
        {"id": "ft_h_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "The machine has been beaten. // Tell the engineers. / Tell the textbooks. / Tell everyone."},
        {"id": "ft_h_ai_02", "mode": "ai", "tone": "calm", "name_before": "calm", "max": 2.5, "text": "Beats the machine."},
        {"id": "ft_a_ai_01", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "The machine prevails. / But it was made to sweat. // If silicon can sweat."},
        {"id": "ft_a_ai_02", "mode": "ai", "tone": "calm", "name_before": None, "max": 2.5, "text": "Victory, for the circuits."},
        {"id": "ft_a_ai_03", "mode": "ai", "tone": "calm", "name_before": None, "max": 3.5, "text": "A lesson. / Delivered in binary."},
        {"id": "ft_win_pvp_01", "mode": "pvp", "tone": "calm", "name_before": "calm", "max": 2.5, "text": "Champion of the lab."},
        {"id": "ft_win_pvp_02", "mode": "pvp", "tone": "calm", "name_before": "calm", "max": 3.0, "text": "Bragging rights, / for a very long time."},
        {"id": "ft_draw_ai", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "Level. / Human and machine walk away as equals. // Tonight, nobody is obsolete."},
        {"id": "ft_draw_pvp", "mode": "pvp", "tone": "calm", "name_before": None, "max": 5.0, "text": "Level. / Two players, one scoreline, / and no loser tonight."},
        {"id": "ft_clean", "mode": "all", "tone": "erupt", "name_before": None, "max": 3.0, "text": "And a clean sheet to go with it!"},
        {"id": "ft_first_ever", "mode": "ai", "tone": "erupt", "name_before": "erupt", "max": 3.5, "text": "The first human ever to beat this machine!"},
        {"id": "ft_record", "mode": "all", "tone": "erupt", "name_before": None, "max": 3.0, "text": "A new name at the top of the leaderboard!"},
        {"id": "ft_record_spd", "mode": "all", "tone": "build", "name_before": None, "max": 3.5, "text": "And a new fastest shot, for the record books!"},
    ])

    # 10.14 Highlights
    lines.extend([
        {"id": "hl_open_01", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "Let us remember. / Let us relive."},
        {"id": "hl_open_02", "mode": "all", "tone": "calm", "name_before": None, "max": 4.5, "text": "Every goal. / Every heartbeat. / One more time."},
        {"id": "hl_min_1", "mode": "all", "tone": "calm", "name_before": None, "max": 2.0, "text": "In the opening minute."},
        {"id": "hl_min_2", "mode": "all", "tone": "calm", "name_before": None, "max": 1.5, "text": "Minute two."},
        {"id": "hl_min_3", "mode": "all", "tone": "calm", "name_before": None, "max": 1.5, "text": "Minute three."},
        {"id": "hl_min_last", "mode": "all", "tone": "calm", "name_before": None, "max": 2.0, "text": "With seconds to go."},
        {"id": "hl_ctx_behind", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "Behind, and running out of time."},
        {"id": "hl_ctx_level", "mode": "all", "tone": "calm", "name_before": None, "max": 3.0, "text": "All square, and everything to play for."},
        {"id": "hl_ctx_ahead", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "In front, and hungry for more."},
        {"id": "hl_ctx_blink_ai", "mode": "ai", "tone": "calm", "name_before": None, "max": 2.5, "text": "The machine had not yet blinked."},
        {"id": "hl_turn", "mode": "all", "tone": "calm", "name_before": None, "max": 4.0, "text": "And this. / This was the moment everything changed."},
        {"id": "hl_w_01", "mode": "all", "tone": "whisper", "name_before": None, "max": 1.5, "text": "Watch it again."},
        {"id": "hl_w_02", "mode": "all", "tone": "whisper", "name_before": None, "max": 3.5, "text": "Look at the angle. / Just look at it."},
        {"id": "hl_w_03", "mode": "all", "tone": "whisper", "name_before": None, "max": 2.5, "text": "Slowly now. / Slowly."},
        {"id": "hl_w_04", "mode": "all", "tone": "whisper", "name_before": None, "max": 2.0, "text": "There. / Right there."},
        {"id": "hl_w_05", "mode": "all", "tone": "whisper", "name_before": None, "max": 3.0, "text": "Nobody could reach that."},
        {"id": "hl_w_ai_01", "mode": "ai", "tone": "whisper", "name_before": None, "max": 4.0, "text": "Watch the machine. / It simply cannot reach."},
        {"id": "hl_tail_01", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "And the laboratory will never be the same."},
        {"id": "hl_tail_02", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "That, is why we play."},
        {"id": "aw_rocket", "mode": "all", "tone": "calm", "name_before": None, "max": 2.0, "text": "The Rocket award."},
        {"id": "aw_wall", "mode": "all", "tone": "calm", "name_before": None, "max": 1.5, "text": "The Wall."},
        {"id": "aw_marathon", "mode": "all", "tone": "calm", "name_before": None, "max": 3.5, "text": "The Marathon. / The longest rally of the match."},
        {"id": "aw_goes", "mode": "all", "tone": "calm", "name_before": None, "max": 1.2, "text": "Goes to."},
        {"id": "hl_close_h_ai", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "History is written by those who dare. // Tonight, a human dared."},
        {"id": "hl_close_a_ai", "mode": "ai", "tone": "calm", "name_before": None, "max": 7.0, "text": "The machine won tonight. // But it will remember this one."},
        {"id": "hl_close_pvp", "mode": "pvp", "tone": "calm", "name_before": None, "max": 7.0, "text": "Two rivals. // One of them will be hearing about this for weeks."},
        {"id": "hl_close_d", "mode": "all", "tone": "calm", "name_before": None, "max": 7.0, "text": "Two sides. / One scoreline. // And a story that is not finished yet."},
        {"id": "hl_end", "mode": "all", "tone": "calm", "name_before": None, "max": 2.5, "text": "Goodnight, from Cheerivy."},
    ])

    return lines


def main():
    parser = argparse.ArgumentParser(description="CHEERIVY Voice Bank Render Script (v2)")
    parser.add_argument("--force", action="store_true", help="Force re-rendering of existing clips")
    parser.add_argument("--only", type=str, default=None, help="Only render clip IDs starting with this prefix")
    parser.add_argument("--skip-names", action="store_true", help="Skip pre-rendering name clips")
    parser.add_argument("--whisper-check", action="store_true", help="Run Whisper ASR check for WER")
    args = parser.parse_args()

    os.makedirs(os.path.join(VOICE_BANK_DIR, "calm"), exist_ok=True)
    os.makedirs(os.path.join(VOICE_BANK_DIR, "build"), exist_ok=True)
    os.makedirs(os.path.join(VOICE_BANK_DIR, "erupt"), exist_ok=True)
    os.makedirs(os.path.join(VOICE_BANK_DIR, "whisper"), exist_ok=True)
    os.makedirs(NAMES_DIR, exist_ok=True)

    # Load ref texts
    ref_texts_file = os.path.join(VOICE_REFS_DIR, "ref_texts.json")
    if os.path.exists(ref_texts_file):
        with open(ref_texts_file) as f:
            ref_texts_map = json.load(f)
    else:
        ref_texts_map = {}

    # Initialize F5-TTS
    print("[*] Initializing F5-TTS model on Apple Silicon (MPS)...")
    from f5_tts.api import F5TTS
    f5 = F5TTS(device="mps")
    print("[+] F5-TTS model loaded successfully.")

    # Pre-render Fallback and Team Names
    if not args.skip_names and (args.only is None or args.only == "names"):
        print("\n[*] Pre-rendering Fallback and Team Names (3 tones each)...")
        all_names_to_render = FALLBACK_NAMES + TEAM_NAMES
        for idx, n in enumerate(all_names_to_render, 1):
            print(f"  [{idx}/{len(all_names_to_render)}] Rendering name: {n['name']} (say: {n['say']})")
            render_single_name(name=n["name"], say_like=n["say"], f5_engine=f5)
        print("[✓] All fallback and team names rendered!\n")

    if args.only == "names":
        return

    # Optionally load Whisper
    whisper_model = None
    if args.whisper_check:
        import whisper
        print("[*] Loading Whisper model (base)...")
        whisper_model = whisper.load_model("base")

    # Load existing manifest v2
    manifest_path = os.path.join(VOICE_BANK_DIR, "manifest.json")
    qa_path = os.path.join(VOICE_BANK_DIR, "qa_report.csv")
    
    manifest_data = {
        "version": 2,
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
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path) as f:
                old_m = json.load(f)
                manifest_data["clips"] = old_m.get("clips", [])
                for c in manifest_data["clips"]:
                    existing_clips[c["id"]] = c
        except Exception:
            pass

    all_lines = get_all_spec_lines()
    if args.only:
        all_lines = [x for x in all_lines if x["id"].startswith(args.only)]

    total_items = len(all_lines)
    print(f"[*] Total bank clips to process: {total_items}")

    qa_rows = []

    for idx, item in enumerate(all_lines, 1):
        cid = item["id"]
        mode = item["mode"]
        tone = item["tone"]
        name_before = item["name_before"]
        max_dur = item["max"]
        raw_text = item["text"]
        tts_text = clean_text(raw_text)
        filename = f"{cid}.wav"
        final_rel_file = f"{tone}/{filename}"
        final_abs_file = os.path.join(VOICE_BANK_DIR, tone, filename)

        tone_cfg = TONE_CONFIG.get(tone, TONE_CONFIG["calm"])
        ref_file_rel = tone_cfg["ref_file"]
        ref_file_abs = os.path.join(VOICE_REFS_DIR, ref_file_rel)
        ref_text = ref_texts_map.get(tone, "It's penalties. We go to the wire and beyond. Some can barely stand. Some are reduced to prayer.")

        clip_hash = compute_clip_hash(tts_text, tone, ref_file_rel)

        # Hash-based skip check (Section 4 Rule 7)
        if not args.force and os.path.exists(final_abs_file) and cid in existing_clips:
            if existing_clips[cid].get("hash") == clip_hash:
                print(f"[{idx}/{total_items}] SKIP {cid} (hash match)")
                continue

        print(f"[{idx}/{total_items}] RENDERING {cid} ({tone}, mode:{mode}) ... \"{tts_text}\"")

        best_stats = None
        best_wer = 0.0
        asr_text = ""
        best_seed = 1

        # Render take (seed 1, retries on fail)
        take_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        render_line(
            f5_engine=f5,
            ref_wav=ref_file_abs,
            ref_text=ref_text,
            full_raw_text=raw_text,
            speed=tone_cfg["speed"],
            seed=1,
            final_take_path=take_file
        )

        stats = post_process_audio(take_file, final_abs_file, tone)
        if os.path.exists(take_file):
            os.remove(take_file)

        # Check QA
        if whisper_model:
            res = whisper_model.transcribe(final_abs_file)
            asr_text = res.get("text", "").strip()
            best_wer = word_error_rate(tts_text, asr_text)

        flags = []
        if stats["duration_ms"] > (max_dur * 1000 * 1.25):
            flags.append("duration_exceeded")
        if best_wer > 0.25 and whisper_model:
            flags.append("high_wer")

        clip_record = {
            "id": cid,
            "file": final_rel_file,
            "category": cid.split("_")[0],
            "mode": mode,
            "tone": tone,
            "name_before": name_before,
            "text": raw_text,
            "tts_text": tts_text,
            "hash": clip_hash,
            "duration_ms": stats["duration_ms"],
            "peak_offset_ms": stats["peak_offset_ms"],
            "lufs": stats["lufs"],
            "seed": best_seed,
            "asr_text": asr_text,
            "wer": round(best_wer, 3),
            "flags": flags
        }

        existing_clips[cid] = clip_record
        manifest_data["clips"] = list(existing_clips.values())

        # Atomic manifest write
        tmp_m = manifest_path + ".tmp"
        with open(tmp_m, "w") as f:
            json.dump(manifest_data, f, indent=2)
        os.replace(tmp_m, manifest_path)

        needs_human = "yes" if (tone == "erupt" or flags) else "no"
        qa_rows.append([
            cid, final_rel_file, mode, tone,
            stats["duration_ms"],
            int(max_dur * 1000),
            round(best_wer, 3),
            best_seed,
            ";".join(flags),
            needs_human
        ])

    # Write QA Report CSV
    with open(qa_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "file", "mode", "tone", "duration_ms", "max_duration_ms", "wer", "seed", "flags", "needs_human_listen"])
        writer.writerows(qa_rows)

    print(f"\n[✓] All voice bank clips rendered successfully in {VOICE_BANK_DIR}!")


if __name__ == "__main__":
    main()
