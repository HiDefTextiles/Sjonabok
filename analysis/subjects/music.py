"""An original background tune for the reel, in the manner of Icelandic tvísöngur.

    python music.py OUT.wav [SECONDS]

Tvísöngur, the old Icelandic two-part singing heard from the 1600s to the 1800s, moves in
parallel fifths and often uses the Lydian mode (F with B natural). This tune is newly written,
not a copy of any song: a melody of eight four-beat bars in F Lydian, a lower voice a fifth
below that meets it on the octave at the start and the end, and a soft drone on F and C as
from a langspil. The tempo is set so the tune fills SECONDS (default 29.1, the reel), with a
short fade at both ends.
"""
import sys
import wave

import numpy as np

SR = 44100
F3, C4, F4, G4, A4, B4, C5, D5, E5, F5 = 53, 60, 65, 67, 69, 71, 72, 74, 76, 77

# eight bars of four beats: (MIDI note, beats)
MELODY = [
    (C5, 2), (A4, 1), (C5, 1),       (D5, 2), (C5, 2),
    (A4, 1), (B4, 1), (C5, 1), (A4, 1), (G4, 4),
    (A4, 1), (C5, 1), (D5, 2),       (E5, 1), (D5, 1), (C5, 2),
    (B4, 1), (A4, 1), (G4, 1), (A4, 1), (F4, 4),
]
# lower voice: the fifth below; F and the last note in octaves, as tvísöngur closes
FIFTH_BELOW = {F4: F3, G4: C4, A4: 62, B4: 64, C5: F4, D5: G4, E5: A4, F5: F4}


class Tvisongur:
    def __init__(self, seconds=29.1):
        beats = sum(b for _, b in MELODY)
        self.beat = seconds / beats
        self.seconds = seconds

    @staticmethod
    def hz(m):
        return 440 * 2 ** ((m - 69) / 12)

    def voice(self, m, dur, bright):
        """A soft bowed or sung tone: few overtones, slow vibrato, gentle start and end."""
        n = int(dur * SR)
        t = np.arange(n) / SR
        f = self.hz(m) * (1 + 0.003 * np.sin(2 * np.pi * 5 * t) * np.clip(t / 0.5, 0, 1))
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = sum((bright ** k) / k * np.sin(k * ph) for k in range(1, 6))
        env = np.minimum(1, t / 0.12) * np.clip((dur - t) / 0.18, 0, 1)
        return s * env

    def line(self, notes, lower=False):
        parts = []
        for i, (m, b) in enumerate(notes):
            last = i == len(notes) - 1
            mm = (m - 12 if last else FIFTH_BELOW[m]) if lower else m
            parts.append(self.voice(mm, b * self.beat, 0.45 if lower else 0.4))
        return np.concatenate(parts)

    def render(self):
        top = self.line(MELODY)
        bot = self.line(MELODY, lower=True)
        n = min(len(top), len(bot))
        t = np.arange(n) / SR
        drone = 0.3 * (np.sin(2 * np.pi * self.hz(41) * t) + 0.5 * np.sin(2 * np.pi * self.hz(48) * t))
        mix = 0.5 * top[:n] + 0.38 * bot[:n] + drone
        fade = np.minimum(1, t / 1.0) * np.clip((self.seconds - t) / 2.0, 0, 1)
        mix *= fade
        return mix / (np.abs(mix).max() * 1.4)       # quiet: background music

    def write(self, path):
        pcm = (self.render() * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    Tvisongur(float(sys.argv[2]) if len(sys.argv) > 2 else 29.1).write(sys.argv[1])
