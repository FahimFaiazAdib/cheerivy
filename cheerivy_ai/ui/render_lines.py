"""
Render the written commentary lines (ui/commentary.py) in the same F5-TTS voice as the voice bank:
same reference clips (show/voice_refs, made from Tahmid's voice), same clean-up (show/render_bank.py).

    cd cheerivy_ai/ui
    HF_HUB_OFFLINE=1 uv run --python 3.12 --with f5-tts --with soundfile python render_lines.py
    python render_lines.py --list          (just show what would be rendered, no F5 needed)

Every line is rendered in every form the game can say it (each name, freeze length, match length ...).
Output: ui/voice/<key>.wav + ui/voice/index.json. Already rendered lines are skipped, so it can be
stopped and started again. The files are the team's voice: keep them off GitHub (ui/voice is ignored).
"""
import argparse
import itertools
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHOW = os.path.join(os.path.dirname(HERE), "show")
sys.path[:0] = [HERE, SHOW]
from commentary import LINES, MINUTES, RENDERED_DIR, TONE, W, cap, written_key  # noqa: E402

NAMES = ("Player One", "Player Two", "the machine", "the challenger")
HUMANS = ("Player One", "Player Two")
PAIRS = (("Player One", "the machine"), ("the machine", "Player One"),
         ("Player One", "Player Two"), ("Player Two", "Player One"),
         ("the challenger", "the machine"), ("the machine", "the challenger"))     # AI vs AI
SINGLE = {"kickoff": ("Player One",), "place": HUMANS, "rest": HUMANS, "goal": HUMANS,
          "goal_beats_ai": ("Player One",), "kickoff_aivai": ("the challenger",),
          "place_aivai": ("the challenger", "the machine"), "rest_side": ("the challenger",)}   # else every name
NUMBERS = {"unbeaten": range(5, 11), "next_big": range(2, 5), "rally_more": range(17, 33, 5)}
FREEZE_S = (3,)          # the default freeze length (other settings: subtitle only)
RECORDED_ENOUGH = {"goal", "goal_beats_ai", "goal_ai"}   # the voice bank already has plenty of these
NOT_SPOKEN = {"a", "b", "hi", "lo", "t"}     # score fallbacks (recordings cover them) and captions


def forms(moment, template):
    """Every {placeholder} filling the game can use -> list of kwargs."""
    fields = set(re.findall(r"{(\w+)}", template))
    if fields & NOT_SPOKEN or moment.startswith("hl_") or moment in RECORDED_ENOUGH:
        return []
    axes = []
    for pair in (("p", "v"), ("lead", "trail")):
        if set(pair) <= fields:
            axes.append([dict(zip(pair, x)) for x in PAIRS])
            fields -= set(pair)
    for f in sorted(fields):
        if f in ("p", "v", "lead", "trail"):
            vals = SINGLE.get(moment, NAMES)
        elif f == "fs":
            vals = FREEZE_S
        elif f == "mins":
            vals = tuple(MINUTES.values())
        elif f == "n":
            vals = tuple(NUMBERS.get(moment, ()))
        else:
            vals = ()
        axes.append([{f: v} for v in vals])
    out = []
    for combo in itertools.product(*axes):
        kw = {}
        for d in combo:
            kw.update(d)
        out.append(kw)
    return out


def all_lines():
    """[(key, text, tone)] for every written line in every form."""
    seen, out = set(), []
    for moment, opts in LINES.items():
        for i, o in enumerate(opts):
            if not isinstance(o, str):
                continue
            for kw in forms(moment, o):
                text = o.format(**{k: (W(v) if isinstance(v, int) else v) for k, v in kw.items()})
                text = re.sub(r"([.!?…] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), cap(text))
                key = written_key(moment, i, text)
                if key not in seen:
                    seen.add(key)
                    out.append((key, text, TONE.get(moment, "calm")))
    return out


MAX_CHARS = 120           # F5 splits longer text into pieces itself, and on the Mac (MPS) that crashes
SENTENCE_GAP_S = 0.25


def pieces(text):
    """Whole sentences, joined while they fit in MAX_CHARS."""
    out, cur = [], ""
    for sent in re.findall(r"[^.!?]+[.!?]+", text) or [text]:
        sent = sent.strip()
        if cur and len(cur) + 1 + len(sent) > MAX_CHARS:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def render_long(rb, f5, ref_wav, ref_text, text, speed, out):
    """One model call per piece; pieces joined with a short breath."""
    import numpy as np
    import soundfile as sf
    parts = pieces(text)
    if len(parts) == 1:
        rb.render_line(f5, ref_wav, ref_text, text, speed, 1, out)
        return
    audio, sr = [], 24000
    for part in parts:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        rb.render_line(f5, ref_wav, ref_text, part, speed, 1, tmp)
        a, sr = sf.read(tmp)
        os.remove(tmp)
        if audio:
            audio.append(np.zeros(int(sr * SENTENCE_GAP_S)))
        audio.append(a if a.ndim == 1 else a[:, 0])
    sf.write(out, np.concatenate(audio), sr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="only list the lines")
    ap.add_argument("--only", help="only keys starting with one of these (comma separated)")
    args = ap.parse_args()
    lines = all_lines()
    if args.only:
        lines = [x for x in lines if x[0].startswith(tuple(args.only.split(",")))]
    os.makedirs(RENDERED_DIR, exist_ok=True)
    index_path = os.path.join(RENDERED_DIR, "index.json")
    try:
        with open(index_path) as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {}
    todo = [x for x in lines if not (x[0] in index and os.path.exists(os.path.join(RENDERED_DIR, x[0] + ".wav")))]
    print(f"{len(lines)} lines, {len(lines) - len(todo)} already rendered, {len(todo)} to render")
    if args.list:
        for key, text, tone in todo:
            print(f"  {tone:6s} {key:32s} {text}")
        return

    import render_bank as rb
    with open(os.path.join(rb.VOICE_REFS_DIR, "ref_texts.json")) as f:
        ref_texts = json.load(f)
    from f5_tts.api import F5TTS
    print("[*] loading F5-TTS ...")
    f5 = F5TTS(device="mps")
    for n, (key, text, tone) in enumerate(todo, 1):
        cfg = rb.TONE_CONFIG[tone]
        print(f"[{n}/{len(todo)}] {tone:6s} {key}  {text}")
        take = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        render_long(rb, f5, os.path.join(rb.VOICE_REFS_DIR, cfg["ref_file"]), ref_texts.get(tone, ""),
                    text, cfg["speed"], take)
        stats = rb.post_process_audio(take, os.path.join(RENDERED_DIR, key + ".wav"), tone)
        os.remove(take)
        index[key] = {"text": text, "tone": tone, "duration_ms": stats["duration_ms"]}
        with open(index_path + ".tmp", "w") as f:
            json.dump(index, f, indent=1, sort_keys=True)
        os.replace(index_path + ".tmp", index_path)
    print(f"[done] {len(index)} lines in {RENDERED_DIR}")


if __name__ == "__main__":
    main()
