"""The generated click and whoosh: length, level, stereo, movement and determinism; no network."""
import array
import importlib.util
import math
import tempfile
import unittest
import wave
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sfx.py"
spec = importlib.util.spec_from_file_location("sfx", SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SoundEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, effect):
        with wave.open(str(s.write(effect, self.root / f"{effect}.wav")), "rb") as w:
            self.assertEqual((w.getframerate(), w.getnchannels()), (48000, 2))
            pcm = array.array("h", w.readframes(w.getnframes()))
        return [v / 32767 for v in pcm[0::2]], [v / 32767 for v in pcm[1::2]]

    def rms(self, values):
        return math.sqrt(sum(v * v for v in values) / max(1, len(values)))

    def test_click_is_short_and_soft(self):
        left, right = self.read("click")
        self.assertEqual(left, right)
        self.assertAlmostEqual(max(map(abs, left)), .56, delta=.01)  # about -5 dBFS
        self.assertLess(len(left) / 48000, .2)
        # Gone in about 0.15 s: its tail is 40 dB under its start.
        self.assertLess(self.rms(left[7200:]), self.rms(left[:2400]) / 100)

    def test_whoosh_swells_dies_away_and_moves_left_to_right(self):
        left, right = self.read("whoosh")
        self.assertAlmostEqual(len(left) / 48000, .55, delta=.001)
        self.assertAlmostEqual(max(map(abs, left + right)), .79, delta=.01)  # about -2 dBFS
        start, middle, end = (self.rms(left[a:b] + right[a:b]) for a, b in ((0, 2400), (7200, 12000), (21600, 26400)))
        self.assertGreater(middle, 4 * start)
        self.assertGreater(middle, 10 * end)
        half = len(left) // 2
        self.assertGreater(self.rms(left[:half]), self.rms(right[:half]))
        self.assertGreater(self.rms(right[half:]), self.rms(left[half:]))
        self.assertLess(max(map(abs, left[-48:] + right[-48:])), .001)

    def test_effects_are_deterministic(self):
        for effect in ("click", "whoosh"):
            a, b = s.write(effect, self.root / "a.wav"), s.write(effect, self.root / "b.wav")
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_rejects_unknown_effects(self):
        with self.assertRaisesRegex(ValueError, "click or whoosh"):
            s.write("boom", self.root / "x.wav")


if __name__ == "__main__":
    unittest.main()
