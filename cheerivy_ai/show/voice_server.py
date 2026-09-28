"""
Kokoro TTS worker (runs under Python 3.12 via uv, because Kokoro doesn't support 3.13 yet).

Started by voice.py:
    uv run --python 3.12 --with kokoro --with soundfile python voice_server.py

stdin : one JSON per line  {"text": "...", "out": "/path/file.wav", "voice": "bm_george"}
stdout: one JSON per line  {"out": "...", "ok": true, "dur": 2.4}   (first line: {"ready": true})
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_OFFLINE", "1")   # model already cached; don't hit the network

import numpy as np          # noqa: E402
import soundfile as sf      # noqa: E402
from kokoro import KPipeline  # noqa: E402

RATE = 24000


def say(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    pipe = KPipeline(lang_code="b", repo_id="hexgrad/Kokoro-82M")   # "b" = British English
    list(pipe("Ready.", voice="bm_george"))                           # warm-up
    say({"ready": True})
    for line in sys.stdin:
        try:
            job = json.loads(line)
            chunks = [a.numpy() for _, _, a in pipe(job["text"], voice=job.get("voice", "bm_george"),
                                                    speed=job.get("speed", 1.0))]
            audio = np.concatenate(chunks) if chunks else np.zeros(RATE // 10, np.float32)
            tmp = job["out"] + ".part.wav"
            sf.write(tmp, audio, RATE)
            os.replace(tmp, job["out"])
            say({"out": job["out"], "ok": True, "dur": len(audio) / RATE})
        except Exception as e:  # keep serving even if one line fails
            say({"out": job.get("out") if isinstance(job, dict) else None, "ok": False, "err": str(e)})


if __name__ == "__main__":
    main()
