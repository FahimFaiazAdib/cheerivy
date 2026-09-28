"""
Voice commentary: Kokoro TTS, British voice "bm_george".

Kokoro needs Python <= 3.12, so it runs as a small worker process (voice_server.py)
started through `uv`. Loading takes a while, so until it is ready (or if it can't start)
lines are spoken with the system voice instead: macOS `say` (voice Daniel) on a Mac,
the built-in Windows voice (System.Speech through PowerShell) on Windows.

Every line is rendered to a sound file in show/cache/voice/ and reused, so the same line is
only synthesised once. The same files can go into the exported highlight video later.
Playback: `afplay` on a Mac, `winsound` on Windows.
"""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import wave

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import winsound

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "voice")
KOKORO_VOICE = "bm_george"
FALLBACK_VOICE = "Daniel"     # macOS British male voice
FALLBACK_NAME = "Windows voice" if IS_WIN else "macOS say"
FALLBACK_EXT = "wav" if IS_WIN else "aiff"


def _system_tts(text, out):
    """Render `text` to the file `out` with the operating system's own voice. Raises on failure."""
    if IS_WIN:
        q = lambda s: s.replace("'", "''")            # PowerShell single-quote escaping
        ps = ("Add-Type -AssemblyName System.Speech;"
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male) } catch {};"
              f"$s.SetOutputToWaveFile('{q(out)}'); $s.Speak('{q(text)}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       timeout=20, check=True, capture_output=True, creationflags=0x08000000)  # no console window
    else:
        subprocess.run(["say", "-v", FALLBACK_VOICE, "-r", "185", "-o", out, text],
                       timeout=15, check=True, capture_output=True)


def _wav_seconds(path):
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, wave.Error, EOFError):
        return 3.0


def _find_uv():
    for p in (shutil.which("uv"), os.path.expanduser("~/.local/bin/uv"), "/opt/homebrew/bin/uv"):
        if p and os.path.exists(p):
            return p
    return None


class Voice:
    def __init__(self, enabled=True, use_kokoro=True, speed=1.05):
        self.enabled = enabled
        self.speed = speed
        self.ready = False            # Kokoro worker loaded
        self.status = "off" if not enabled else "starting"
        self._proc = None
        self._wlock = threading.Lock()
        self._done = {}               # out path -> threading.Event
        self._play_q = queue.PriorityQueue()
        self._seq = 0
        self._current = None          # running afplay process (Mac)
        self._win_stop = threading.Event()   # set by hush() to cut a Windows line short
        self._gen = 0                 # bumped by hush(): a recorded sequence stops between files
        self._stop = False
        os.makedirs(CACHE, exist_ok=True)
        if not enabled:
            return
        if use_kokoro:
            threading.Thread(target=self._start_kokoro, daemon=True).start()
        else:
            self.status = FALLBACK_NAME
        threading.Thread(target=self._player, daemon=True).start()

    # ------------------------------------------------------------ Kokoro worker
    def _start_kokoro(self):
        uv = _find_uv()
        if not uv:
            self.status = f"{FALLBACK_NAME} (uv not found)"
            return
        cmd = [uv, "run", "--quiet", "--python", "3.12", "--with", "kokoro", "--with", "soundfile",
               "python", os.path.join(HERE, "voice_server.py")]
        try:
            log = open(os.path.join(HERE, "cache", "voice_server.log"), "w")
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                          text=True, bufsize=1, env={**os.environ, "HF_HUB_OFFLINE": "1"})
        except OSError as e:
            self.status = f"{FALLBACK_NAME} ({e})"
            return
        self.status = "loading George..."
        for line in self._proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("ready"):
                self.ready = True
                self.status = "Kokoro · George"
                print("[voice] Kokoro ready (bm_george)")
            elif msg.get("out"):
                ev = self._done.get(msg["out"])
                if ev:
                    ev.set()
        self.ready = False
        if not self._stop:
            self.status = f"{FALLBACK_NAME} (Kokoro stopped, see show/cache/voice_server.log)"

    # ------------------------------------------------------------ synthesis
    def _path(self, text, engine):
        h = hashlib.sha1(f"{engine}|{KOKORO_VOICE}|{self.speed}|{text}".encode()).hexdigest()[:16]
        return os.path.join(CACHE, f"{h}.{'wav' if engine == 'kokoro' else FALLBACK_EXT}")

    def cached(self, text):
        """Path of an already-rendered file for this line (Kokoro preferred), else None."""
        for engine in ("kokoro", "say"):
            p = self._path(text, engine)
            if os.path.exists(p):
                return p
        return None

    def _request(self, text):
        """Ask Kokoro for a line; returns (path, Event) or None if Kokoro isn't ready."""
        if not self.ready:
            return None
        out = self._path(text, "kokoro")
        if os.path.exists(out):
            ev = threading.Event()
            ev.set()
            return out, ev
        ev = self._done.setdefault(out, threading.Event())
        try:
            with self._wlock:
                self._proc.stdin.write(json.dumps({"text": text, "out": out, "voice": KOKORO_VOICE,
                                                   "speed": self.speed}) + "\n")
                self._proc.stdin.flush()
        except (OSError, ValueError):
            self.ready = False
            return None
        return out, ev

    def prepare(self, lines):
        """Pre-render lines in the background (e.g. the goal calls once names are known)."""
        if not self.enabled:
            return

        def work():
            deadline = time.time() + 120
            while not self.ready and time.time() < deadline and not self._stop:
                time.sleep(0.5)
            for t in lines:
                if self._stop:
                    return
                r = self._request(t)
                if r:
                    r[1].wait(15)
        threading.Thread(target=work, daemon=True).start()

    def render(self, text, wait=8.0):
        """Blocking: file for this line (Kokoro if possible, else `say`)."""
        p = self.cached(text)
        if p:
            return p
        r = self._request(text)
        if r and r[1].wait(wait) and os.path.exists(r[0]):
            return r[0]
        out = self._path(text, "say")
        try:
            _system_tts(text, out)
            return out if os.path.exists(out) else None
        except (OSError, subprocess.SubprocessError):
            return None

    # ------------------------------------------------------------ playback
    def say(self, text, priority=5, max_age=4.0, interrupt=False):
        """Queue a line. Lower priority number = spoken first. Lines older than max_age are dropped."""
        if not self.enabled or not text:
            return
        if interrupt:
            self.hush()
        self._seq += 1
        self._play_q.put((priority, self._seq, time.time(), max_age, text))

    def play(self, paths, priority=5, max_age=4.0, interrupt=False):
        """Queue recorded clips (e.g. a name, then a line), played back to back as one item."""
        if not self.enabled or not paths:
            return
        if interrupt:
            self.hush()
        self._seq += 1
        self._play_q.put((priority, self._seq, time.time(), max_age, tuple(paths)))

    def hush(self):
        """Stop the current line and forget queued ones."""
        self._gen += 1
        try:
            while True:
                self._play_q.get_nowait()
        except queue.Empty:
            pass
        if IS_WIN:
            self._win_stop.set()
            try:
                winsound.PlaySound(None, 0)           # stop whatever is playing
            except RuntimeError:
                pass
            return
        p = self._current
        if p and p.poll() is None:
            p.terminate()

    def _play(self, path):
        """Play one file and return when it's done (or cut short by hush())."""
        if IS_WIN:
            self._win_stop.clear()
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            self._win_stop.wait(_wav_seconds(path) + 0.1)
            return
        self._current = subprocess.Popen(["afplay", path])
        self._current.wait()

    def _player(self):
        while not self._stop:
            try:
                _, _, created, max_age, text = self._play_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if isinstance(text, tuple):                 # recorded clips from the voice bank
                if time.time() - created > max_age:
                    continue
                gen = self._gen
                for path in text:
                    if gen != self._gen or self._stop:    # hush() arrived: drop the rest
                        break
                    try:
                        self._play(path)
                    except (OSError, RuntimeError):
                        pass
                continue
            path = self.render(text, wait=max(1.0, max_age - (time.time() - created)))
            if not path or time.time() - created > max_age:
                continue
            try:
                self._play(path)
            except (OSError, RuntimeError):
                pass

    def close(self):
        self._stop = True
        self.hush()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
            self._proc.terminate()
