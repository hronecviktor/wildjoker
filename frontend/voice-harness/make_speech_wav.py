"""Write speech.wav: a speech-like test signal for Chromium's fake microphone.

Chromium's default fake microphone only beeps for ~50 ms a second, which the
speaking detector rightly ignores. This makes 0.7 s "syllables" (a voiced
tone with harmonics and vibrato) separated by 0.5 s of silence.
"""

import math
import struct
import sys
import wave

RATE = 48_000


def samples(seconds: float = 6.0):
    for n in range(int(seconds * RATE)):
        t = n / RATE
        phase = t % 1.2
        if phase >= 0.7:
            yield 0.0
            continue
        envelope = math.sin(math.pi * phase / 0.7) ** 0.5
        f0 = 150 + 20 * math.sin(2 * math.pi * 5 * t) + 30 * math.sin(2 * math.pi * 0.4 * t)
        yield envelope * sum(
            0.3 / k * math.sin(2 * math.pi * f0 * k * t) for k in range(1, 8)
        )


def main(path: str) -> None:
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(struct.pack("<h", int(32767 * 0.8 * s)) for s in samples()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "speech.wav")
