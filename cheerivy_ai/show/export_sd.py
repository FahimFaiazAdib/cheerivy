"""
Make the microSD card for the robot's DFPlayer Mini (commentary + stadium crowd).

    python show/export_sd.py            (from cheerivy_ai/)  -> show/sd_card/

The DFPlayer plays one file at a time, so the crowd works like this:
  * the crowd murmur is the MAIN track, looping in the background ("P<n>;" from the laptop)
  * every commentary clip is an ADVERT ("A<n>;"): the DFPlayer pauses the crowd, plays the clip,
    then carries on with the crowd by itself. Each advert has a slice of crowd mixed under the
    voice, so the crowd never seems to stop. Goal calls get the goal ROAR underneath instead.

Card layout (copy both folders to the root of the FAT32 card):
    /MP3/0001.mp3 ...     every clip, plain, plus the crowd loop and full-time applause
    /ADVERT/0001.mp3 ...  the same numbers, with crowd mixed in
Track numbers are kept in voice_bank/sd_tracks.json (the laptop reads it too). Numbers never
change once given, so new clips are just added at the end.

Crowd recordings: voice_bank/crowd/src/*.mp3, from Pixabay (free under the Pixabay Content License).
Needs ffmpeg (Mac: brew install ffmpeg).
"""
import json
import os
import random
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(HERE, "voice_bank")
CROWD = os.path.join(BANK, "crowd")
SRC = os.path.join(CROWD, "src")
OUT = os.path.join(HERE, "sd_card")
TRACKS = os.path.join(BANK, "sd_tracks.json")
FF = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

# crowd/<name>.wav made from the downloads: (source, loudness LUFS, seconds (None = whole), fade)
CROWD_FILES = {
    "ambience": ("ambience_stadium.mp3", -27, None, True),   # the murmur loop (made 5 min long below)
    "roar": ("goal_roar.mp3", -15, None, True),              # goal explosion
    "applause": ("cheer_stadium.mp3", -19, 25, True),        # after the final whistle
    "whistle": ("whistle.mp3", -17, None, False),
    "ooh1": ("ooh_disappointed.mp3", -19, None, True),
    "ooh2": ("ooh_gasp.mp3", -21, None, True),
}
AMBIENCE_S = 300          # murmur loop length: longer than a match, so it rarely has to restart
BED_DB = 0                # crowd slice under a normal line: the ambience's own level (-27 LUFS)
ROAR_BED_DB = -5          # goal roar under a goal call (-20 LUFS), voices are about -16..-20
GOAL_CLIPS = ("pay_g", "sit_open", "sit_lead", "sit_equal", "sit_comeback", "clk_last")
NO_BED = ("crowd/",)      # crowd sounds themselves: no extra crowd under them


def ff(*args):
    subprocess.run([FF, "-y", "-loglevel", "error", *args], check=True)


def seconds(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def make_crowd():
    """Level and trim the downloaded crowd sounds into voice_bank/crowd/*.wav (44.1 kHz stereo)."""
    for name, (src, lufs, dur, fade) in CROWD_FILES.items():
        out = os.path.join(CROWD, f"{name}.wav")
        s = os.path.join(SRC, src)
        if not os.path.exists(s):
            print("missing", s)
            continue
        if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(s):
            continue
        af = [f"loudnorm=I={lufs}:TP=-1.5:LRA=11"]
        if dur:
            af.insert(0, f"atrim=0:{dur}")
        if fade:
            af.append("afade=t=in:d=0.3")
            if dur:
                af.append(f"afade=t=out:st={dur - 2}:d=2")
        tmp = out + ".tmp.wav"
        ff("-i", s, "-af", ",".join(af), "-ar", "44100", "-ac", "2", tmp)
        if name == "ambience":             # loop to AMBIENCE_S with 4 s crossfades so the seam isn't heard
            L = seconds(tmp)
            n = int(AMBIENCE_S // (L - 4)) + 1
            inputs, chain = [], ""
            for i in range(n):
                inputs += ["-i", tmp]
            prev = "[0]"
            for i in range(1, n):
                chain += f"{prev}[{i}]acrossfade=d=4[x{i}];"
                prev = f"[x{i}]"
            ff(*inputs, "-filter_complex", chain + f"{prev}atrim=0:{AMBIENCE_S}[o]", "-map", "[o]", out)
            os.remove(tmp)
        else:
            os.replace(tmp, out)
        print("crowd:", name, f"{seconds(out):.1f} s")


def all_clips():
    rels = []
    with open(os.path.join(BANK, "manifest.json")) as f:
        rels += [c["file"] for c in json.load(f)["clips"]]
    with open(os.path.join(BANK, "names", "index.json")) as f:
        for entry in json.load(f).values():
            rels += list(entry["files"].values())
    rels += [f"crowd/{n}.wav" for n in CROWD_FILES]
    return sorted({r for r in rels if os.path.exists(os.path.join(BANK, r))})


def plain(src, dst):
    # 44.1 kHz stereo MP3 plays on every DFPlayer clone; 80 ms of silence in front because some
    # clones swallow the first moment of a track.
    ff("-i", src, "-af", "adelay=80:all=1", "-ar", "44100", "-ac", "2", "-b:a", "128k", dst)


def with_crowd(src, dst, rel, n):
    """Voice + a slice of crowd underneath, faded in and out, so it blends with the paused crowd loop."""
    goal = os.path.basename(rel).startswith(GOAL_CLIPS)
    bed = os.path.join(CROWD, "roar.wav" if goal else "ambience.wav")
    d = seconds(src) + 0.08 + 0.35
    start = 0.0 if goal else random.Random(n).uniform(0, max(0.0, seconds(bed) - d - 1))
    gain = ROAR_BED_DB if goal else BED_DB
    fc = (f"[1]atrim=start={start:.2f}:duration={d:.2f},asetpts=PTS-STARTPTS,volume={gain}dB,"
          f"afade=t=in:d=0.12,afade=t=out:st={d - 0.25:.2f}:d=0.25[b];"
          f"[0]aresample=44100,aformat=channel_layouts=stereo,adelay=80:all=1[v];"
          f"[v][b]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[o]")
    ff("-i", src, "-i", bed, "-filter_complex", fc, "-map", "[o]", "-ar", "44100", "-ac", "2", "-b:a", "128k", dst)


def main():
    if not os.path.exists(FF):
        sys.exit("ffmpeg not found (Mac: brew install ffmpeg)")
    make_crowd()
    try:
        with open(TRACKS) as f:
            tracks = json.load(f)
    except (OSError, ValueError):
        tracks = {}
    for rel in all_clips():
        if rel not in tracks:
            tracks[rel] = max(tracks.values(), default=0) + 1
    if max(tracks.values(), default=0) > 2999:
        sys.exit("more than 2999 clips: too many for the DFPlayer")

    for d in ("MP3", "ADVERT"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    made = 0
    for rel, n in sorted(tracks.items(), key=lambda kv: kv[1]):
        src = os.path.join(BANK, rel)
        if not os.path.exists(src):
            continue
        for folder, fn in (("MP3", plain), ("ADVERT", None if rel.startswith(NO_BED) else with_crowd)):
            dst = os.path.join(OUT, folder, f"{n:04d}.mp3")
            if folder == "ADVERT" and fn is None:
                fn = plain                        # crowd sounds as adverts: as they are
            if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                continue
            if fn is plain:
                plain(src, dst)
            else:
                fn(src, dst, rel, n)
            made += 1
    with open(TRACKS, "w") as f:
        json.dump(tracks, f, indent=1, sort_keys=True)
    print(f"{len(tracks)} tracks ({made} files new or updated) in {OUT}")
    print("Copy the MP3 and ADVERT folders to the root of the FAT32 microSD card.")


if __name__ == "__main__":
    main()
