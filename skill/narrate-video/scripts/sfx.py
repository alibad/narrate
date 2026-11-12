#!/usr/bin/env python3
"""The film's two sound effects, newly synthesised: a soft click for a click on screen and a short whoosh for a card.
Deterministic: no samples and no third-party material, so nothing ships under another licence. Python's standard
library only.

    python sfx.py click click.wav
"""
from __future__ import annotations
import argparse
import array
import math
import random
import wave
from pathlib import Path

RATE = 48000


def band(samples, centre, q, stages=3):
    """A state-variable band-pass, run `stages` times so the hiss above the band falls away; `centre` gives the
    frequency (Hz) for each sample."""
    for _ in range(stages):
        low = mid = 0.0
        out = []
        for x, f in zip(samples, centre):
            k = 2 * math.sin(math.pi * f / RATE)
            low += k * mid
            high = x - low - mid / q
            mid += k * high
            out.append(mid)
        samples = out
    return samples


def click():
    """A soft tick, peak -5 dBFS, gone in about 0.15 s: a band of noise near 2.4 kHz over a short 1.3 kHz knock and a
    low body."""
    n = round(.18 * RATE)
    noise = random.Random(7)
    hiss = band([noise.uniform(-1, 1) for _ in range(n)], [2400] * n, 1.4)
    mono = []
    for i, h in enumerate(hiss):
        t = i / RATE
        attack = min(1, t / .0004)
        mono.append(attack * (h * math.exp(-t / .006) / .06 + .5 * math.sin(2 * math.pi * 1300 * t) * math.exp(-t / .014)
                              + .3 * math.sin(2 * math.pi * 190 * t) * math.exp(-t / .03)) * min(1, (n - i) / (.01 * RATE)))
    return finish(mono, mono, .56)


def whoosh():
    """Air rushing past, 0.55 s: noise through a band that sweeps up from 450 Hz to 1.7 kHz and settles at 700 Hz,
    swelling over the first 0.16 s and dying away by 0.45 s, moving from left to right. Peak -2 dBFS."""
    n = round(.55 * RATE)
    noise = random.Random(11)
    centre = []
    for i in range(n):
        x = i / n
        rise, fall = min(1, x / .36), max(0, (x - .36) / .64)
        centre.append(450 * (1700 / 450) ** (math.sin(math.pi / 2 * rise)) * (700 / 1700) ** (fall * fall * (3 - 2 * fall)))
    air = band([noise.uniform(-1, 1) for _ in range(n)], centre, 1.0)
    left, right = [], []
    for i, a in enumerate(air):
        t, x = i / RATE, i / n
        swell = math.sin(math.pi / 2 * min(1, t / .16)) ** 2
        level = swell * math.exp(-max(0, t - .2) / .075) * min(1, (n - i) / (.03 * RATE))
        pan = .3 + .4 * x
        left.append(a * level * math.cos(pan * math.pi / 2))
        right.append(a * level * math.sin(pan * math.pi / 2))
    return finish(left, right, .79)


def finish(left, right, peak):
    top = max(max(map(abs, left)), max(map(abs, right)), 1e-9)
    return [v * peak / top for v in left], [v * peak / top for v in right]


EFFECTS = {"click": click, "whoosh": whoosh}


def write(effect, destination):
    """Write `effect` ("click" or "whoosh") to `destination` as a 48 kHz stereo WAV."""
    if effect not in EFFECTS:
        raise ValueError(f"effect must be {' or '.join(EFFECTS)}")
    left, right = EFFECTS[effect]()
    pcm = array.array("h", (round(v * 32767) for pair in zip(left, right) for v in pair))
    with wave.open(str(destination), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return Path(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("effect", choices=sorted(EFFECTS))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        write(args.effect, args.output)
    except (ValueError, OSError) as e:
        parser.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
