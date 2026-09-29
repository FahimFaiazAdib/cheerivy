"""
The match sound on the laptop (JBL on aux = no delay): stadium crowd + commentator, through pygame.

    crowd bed     ambience loop, always on; louder with tension (a goal is coming), quieter under the voice
    crowd fx      roar (goal), ooh (close save), gasp, applause (long rally / full time), whistle
    voice         commentary clips in the F5 voice (Tahmid's): the voice bank (show/voice_bank) and the
                  new lines rendered by ui/render_lines.py (ui/voice). A line with no clip is subtitle only.
hush() fades the voice out in 80 ms: a goal never waits for the end of a sentence.
Without pygame (pip install pygame) or without the voice bank everything stays silent, the game still runs.
"""
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CROWD = os.path.join(os.path.dirname(HERE), "show", "voice_bank", "crowd")

BED_VOL, BED_TENSE, BED_DUCK = 0.40, 0.75, 0.18   # crowd: normal / a goal is coming / under the voice
BED_RAMP = 1.5            # volume change per second
FX_VOL = {"roar": 1.0, "ooh": 0.8, "gasp": 0.8, "applause": 0.7, "whistle": 0.9}
FX_FILE = {"roar": "roar.wav", "ooh": "ooh1.wav", "gasp": "ooh2.wav", "applause": "applause.wav",
           "whistle": "whistle.wav"}
HUSH_MS = 80
CLIP_GAP_MS = 140


class Sound:
    def __init__(self, bank, voice_vol=0.8, crowd_vol=0.5):
        self.bank = bank
        self.ok = False
        self.voice_vol, self.crowd_vol = voice_vol, crowd_vol
        self.tension, self.swell_until = 0.0, 0.0
        self.bed_level = 0.0
        self._queue = []           # rest of the current clip sequence
        self._lock = threading.Lock()
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            self.pg = pygame
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self.bed, self.voice, self.fx, self.fx2 = (pygame.mixer.Channel(i) for i in range(4))
            self._cache = {}
            self.ok = True
        except Exception as e:
            print(f"[sound] off ({e}); pip install pygame for crowd + commentary")
            return
        amb = os.path.join(CROWD, "ambience.wav")
        if os.path.exists(amb):
            self.bed.play(self._sound(amb), loops=-1)
            self.bed.set_volume(0.0)
        else:
            print("[sound] no crowd sounds (show/voice_bank/crowd): commentary only")

    def _sound(self, path):
        s = self._cache.get(path)
        if s is None:
            s = self._cache[path] = self.pg.mixer.Sound(path)
        return s

    # ------------------------------------------------------------ crowd
    def crowd(self, what, value=None):
        if not self.ok:
            return
        if what == "tension":
            self.tension = float(value or 0.0)
        elif what == "swell":
            self.swell_until = time.monotonic() + 3.0
        elif what in FX_FILE:
            path = os.path.join(CROWD, FX_FILE[what])
            if os.path.exists(path):
                ch = self.fx if (not self.fx.get_busy() or what == "roar") else self.fx2
                ch.play(self._sound(path))
                ch.set_volume(min(1.0, FX_VOL[what] * self.crowd_vol * 1.6))

    def update(self, dt, now):
        """Call every tick: moves the crowd volume toward where it should be."""
        if not self.ok:
            return
        target = BED_VOL + (BED_TENSE - BED_VOL) * self.tension
        if now < self.swell_until:
            target = BED_TENSE + 0.2
        if self.busy:
            target = min(target, BED_DUCK + 0.3 * self.tension)
        step = BED_RAMP * dt
        self.bed_level += max(-step, min(step, target - self.bed_level))
        self.bed.set_volume(min(1.0, self.bed_level * self.crowd_vol * 2))
        with self._lock:                                   # next clip of a sequence
            if self._queue and not self.voice.get_busy():
                self.voice.play(self._queue.pop(0))
                self.voice.set_volume(self.voice_vol)

    # ------------------------------------------------------------ voice
    @property
    def busy(self):
        return self.ok and (bool(self._queue) or self.voice.get_busy())

    def say(self, key, text):
        """Play a line now. Returns its length in seconds when it's recorded, else None."""
        if not self.ok:
            return None
        files = self.bank.files(key)
        if files:
            self._play(files)
            return self.bank.seconds(key)
        return None                # not rendered in the F5 voice yet: subtitle only, never a robot voice

    def _play(self, files):
        snds = []
        for f in files:
            try:
                snds.append(self._sound(f))
            except Exception:
                pass
        if not snds:
            return
        gap = self.pg.mixer.Sound(buffer=b"\0" * (int(44100 * CLIP_GAP_MS / 1000) * 4))
        seq = [snds[0]]
        for s in snds[1:]:
            seq += [gap, s]
        with self._lock:
            self.voice.play(seq[0])
            self.voice.set_volume(self.voice_vol)
            self._queue = seq[1:]

    def hush(self):
        if not self.ok:
            return
        with self._lock:
            self._queue = []
            self.voice.fadeout(HUSH_MS)

    def voice_busy(self):
        return self.busy
