"""The generated music bed: length, level, stereo, determinism and a seamless loop; no network."""
import array
import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/soundbed.py"
spec = importlib.util.spec_from_file_location("soundbed", SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SoundbedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, path):
        with wave.open(str(path), "rb") as w:
            return w.getframerate(), w.getnchannels(), array.array("h", w.readframes(w.getnframes()))

    def test_bed_has_the_asked_length_and_sits_low(self):
        rate, channels, pcm = self.read(s.bed(30, self.root / "bed.wav"))
        self.assertEqual((rate, channels), (48000, 2))
        self.assertEqual(len(pcm) // 2, 30 * 48000)
        peak = max(map(abs, pcm)) / 32767
        self.assertTrue(.3 < peak < .55, peak)  # about -6 dBFS: room for the voice on top
        # The swell: silent at the very start and end, sounding in the middle.
        self.assertLess(max(map(abs, pcm[:96])), 200)
        self.assertLess(max(map(abs, pcm[-96:])), 200)
        self.assertGreater(max(map(abs, pcm[15 * 96000:15 * 96000 + 9600])), 2000)

    def test_short_bed_sounds_until_its_fade_out(self):
        # A 2 s bed swells in over its first second and out over its last; it is not silent from the middle on.
        _, _, pcm = self.read(s.bed(2, self.root / "short.wav"))
        self.assertGreater(max(map(abs, pcm[2 * 48000:2 * 57600])), 1000)  # 1.0 to 1.2 s
        self.assertLess(max(map(abs, pcm[-96:])), 200)

    def test_bed_is_deterministic(self):
        a, b = s.bed(5, self.root / "a.wav"), s.bed(5, self.root / "b.wav")
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_loop_has_no_seam(self):
        # The loop's last sample runs on into its first: no jump bigger than the bed's own steps.
        left, right = s.loop(84)
        steps = [abs(b - a) for a, b in zip(left, left[1:])]
        self.assertLess(abs(left[0] - left[-1]), 2 * max(steps))
        self.assertLess(abs(right[0] - right[-1]), 2 * max(abs(b - a) for a, b in zip(right, right[1:])))

    def test_rejects_unreasonable_lengths(self):
        for seconds, bpm in ((0, 84), (4000, 84), (10, 500)):
            with self.assertRaisesRegex(ValueError, "bed length"):
                s.bed(seconds, self.root / "x.wav", bpm)


if __name__ == "__main__":
    unittest.main()
