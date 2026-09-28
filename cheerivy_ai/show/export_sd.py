"""
Make the microSD card for the robot's DFPlayer Mini.

    python show/export_sd.py            (from cheerivy_ai/)  -> show/sd_card/MP3/0001.mp3 ...

Every clip of the voice bank (lines and names) gets a track number. The DFPlayer plays
/MP3/<number>.mp3 when the laptop sends "P<number>;". The numbers are kept in
voice_bank/sd_tracks.json, which the laptop reads too, so both sides agree.
Numbers never change once given: new clips are added at the end, so an old card keeps working
for the clips it already has.

Then copy the MP3 folder (the folder itself, not just its files) to the root of the FAT32 card.
Needs ffmpeg (Mac: brew install ffmpeg).
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(HERE, "voice_bank")
OUT = os.path.join(HERE, "sd_card", "MP3")
TRACKS = os.path.join(BANK, "sd_tracks.json")


def all_clips():
    rels = []
    with open(os.path.join(BANK, "manifest.json")) as f:
        rels += [c["file"] for c in json.load(f)["clips"]]
    with open(os.path.join(BANK, "names", "index.json")) as f:
        for entry in json.load(f).values():
            rels += list(entry["files"].values())
    return sorted({r for r in rels if os.path.exists(os.path.join(BANK, r))})


def main():
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(ffmpeg):
        sys.exit("ffmpeg not found (Mac: brew install ffmpeg)")
    try:
        with open(TRACKS) as f:
            tracks = json.load(f)
    except (OSError, ValueError):
        tracks = {}
    for rel in all_clips():
        if rel not in tracks:
            tracks[rel] = max(tracks.values(), default=0) + 1
    if max(tracks.values(), default=0) > 2999:
        sys.exit("more than 2999 clips: the DFPlayer's MP3 folder can't hold them")

    os.makedirs(OUT, exist_ok=True)
    made = 0
    for rel, n in sorted(tracks.items(), key=lambda kv: kv[1]):
        src, dst = os.path.join(BANK, rel), os.path.join(OUT, f"{n:04d}.mp3")
        if not os.path.exists(src):
            continue
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue
        # 44.1 kHz stereo MP3 plays on every DFPlayer clone; 0.08 s of silence in front
        # because some clones swallow the first moment of a track.
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src,
                        "-af", "adelay=80:all=1", "-ar", "44100", "-ac", "2", "-b:a", "128k", dst], check=True)
        made += 1
    with open(TRACKS, "w") as f:
        json.dump(tracks, f, indent=1, sort_keys=True)
    print(f"{len(tracks)} tracks ({made} new or updated) in {OUT}")
    print("Copy the MP3 folder to the root of the FAT32 microSD card.")


if __name__ == "__main__":
    main()
