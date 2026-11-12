#!/usr/bin/env python3
"""A quiet, generated music bed to sit under narration: warm pad chords, a soft bell on each bar and a light
pulse, swelling in at the open and out at the close. No melody, little above 2 kHz but the bells, peak -6 dBFS;
render.py ducks it further under the voice. Deterministic and newly synthesised: no samples, no third-party
material. Python's standard library plus FFmpeg: one seamless loop is synthesised here, FFmpeg repeats it.

    python soundbed.py 182.5 bed.wav [--bpm 84]
"""
from __future__ import annotations
import argparse
import array
import math
import subprocess
import tempfile
import wave
from pathlib import Path

LOOP_RATE = 24000  # the bed has nothing a 12 kHz band misses; FFmpeg resamples to 48 kHz
# D major, two bars a chord: Dmaj9, Bm7, Gmaj7, A(add9); MIDI notes, low to mid.
CHORDS = [[38, 50, 54, 57, 64], [35, 47, 50, 54, 57], [31, 43, 47, 54, 59], [33, 45, 49, 52, 59]]
TABLE = 4096
# A note's tone: the fundamental with a little of the second and third harmonic.
SHAPE = [math.sin(x) + .18 * math.sin(2 * x) + .05 * math.sin(3 * x) for x in (2 * math.pi * i / TABLE for i in range(TABLE))]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def loop(bpm):
    """One period of the bed (four chords, 32 beats) as stereo float lists. Every tail wraps around the end, so the
    loop repeats without a seam."""
    beat = 60 / bpm
    seg = 8 * beat
    n = round(4 * seg * LOOP_RATE)
    left, right = [0.0] * n, [0.0] * n

    def add(start, values, gl, gr):
        for i, v in enumerate(values, start):
            i %= n
            left[i] += v * gl
            right[i] += v * gr

    for k, notes in enumerate(CHORDS):
        start = k * seg
        # Pad: each chord fades in over 1.4 s and out over 1.6 s past its end, so the changes cross-fade.
        a, length = round((start - .2) * LOOP_RATE), round((seg + 1.8) * LOOP_RATE)
        env = [min(1, (j / LOOP_RATE) / 1.4) * min(1, (length - j) / LOOP_RATE / 1.6) for j in range(length)]
        for j, m in enumerate(notes):
            step = hz(m) * (1 + (j - 2) * .0012) * TABLE / LOOP_RATE
            offset = j * TABLE / (2 * math.pi)
            amp = .05 if m < 45 else .032
            tone = [SHAPE[int(offset + i * step) % TABLE] * amp * e for i, e in enumerate(env)]
            pan = .12 * (j - 2) / 2
            add(a, tone, 1 - pan, 1 + pan)
        # A soft bell on the chord's top note an octave up, at each bar.
        f = hz(notes[-1] + 12)
        for bar in (0, 4):
            t0 = start + bar * beat
            bell = [.018 * math.exp(-x / .7) * min(1, x / .004) * (math.sin(2 * math.pi * f * x) + .3 * math.sin(2 * math.pi * 2.01 * f * x) * math.exp(-x / .2))
                    for x in (i / LOOP_RATE for i in range(round(2.5 * LOOP_RATE)))]
            add(round(t0 * LOOP_RATE), bell, .9, 1.1)
    # A light pulse on beats one and three.
    pulse, phase = [], 0.0
    for i in range(round(.35 * LOOP_RATE)):
        x = i / LOOP_RATE
        phase += 2 * math.pi * (48 + 60 * math.exp(-x / .03)) / LOOP_RATE
        pulse.append(.07 * math.exp(-x / .12) * math.sin(phase))
    for b in range(0, 32, 2):
        add(round(b * beat * LOOP_RATE), pulse, 1, 1)
    return left, right


def bed(seconds, destination, bpm=84):
    """Write a 48 kHz stereo bed of `seconds` to `destination` (WAV)."""
    if not 1 <= seconds <= 3600 or not 40 <= bpm <= 200:
        raise ValueError("bed length must be 1 to 3600 seconds and bpm 40 to 200")
    left, right = loop(bpm)
    peak = max(max(map(abs, left)), max(map(abs, right)), 1e-9)
    gain = .5 * 32767 / peak
    pcm = array.array("h", (round(v * gain) for pair in zip(left, right) for v in pair))
    with tempfile.TemporaryDirectory(prefix="soundbed-") as work:
        source = Path(work) / "loop.wav"
        with wave.open(str(source), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(LOOP_RATE)
            w.writeframes(pcm.tobytes())
        swell_in, swell_out = min(3.5, seconds / 2), min(3, seconds / 2)
        # Air: a little low-passed noise so the bed doesn't sound sterile. Then the swell in and out.
        graph = (f"[0:a]aresample=48000[bed];anoisesrc=r=48000:a=.004:c=pink:s=7:d={seconds:.3f},lowpass=f=900,aformat=channel_layouts=stereo[air];"
                 f"[bed][air]amix=inputs=2:normalize=0:duration=shortest,atrim=end={seconds:.3f},"
                 f"afade=t=in:d={swell_in:.3f},afade=t=out:st={seconds - swell_out:.3f}:d={swell_out:.3f}[out]")
        result = subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", source, "-filter_complex", graph, "-map", "[out]",
                                 "-c:a", "pcm_s16le", "-ar", "48000", str(destination)], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"ffmpeg failed making the music bed: {result.stderr[-800:]}")
    return Path(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("seconds", type=float)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bpm", type=float, default=84)
    args = parser.parse_args()
    try:
        bed(args.seconds, args.output, args.bpm)
    except (ValueError, OSError) as e:
        parser.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
