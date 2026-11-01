"""Behavioral checks using original synthetic fixtures; no browser or network."""
import importlib.util
import json
import math
import struct
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops, ImageStat

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/render.py"
spec = importlib.util.spec_from_file_location("renderer", SCRIPT)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = Image.new("RGB", (900, 500), "#edf1f5")
        draw = ImageDraw.Draw(self.image)
        draw.rectangle((30, 40, 400, 450), fill="#123a50")
        draw.text((50, 60), "SYNTHETIC EXAMPLE", fill="white")
        self.image.save(self.root / "still.png")
        with wave.open(str(self.root / "voice.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(48000)
            f.writeframes(b"".join(struct.pack("<h", round(5000*math.sin(2*math.pi*440*n/48000))) for n in range(48000)))
        self.plan = {"version": 1, "width": 640, "height": 360, "fps": 30, "scenes": [{"kind": "still", "status": "demonstration", "title": "A stable hold", "visual": "still.png", "audio": "voice.wav", "say": "Synthetic test audio, not speech.", "minDuration": 2, "captions": [{"start": 0, "end": 1, "text": "A synthetic test fixture."}, {"start": 1, "end": 2, "text": "The UI stays in place."}]}]}
        self.path = self.root / "plan.json"
        self.plan['voice'] = dict(provider='test',model='tone-fixture',revision='1',name='not-speech',language='none')

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.plan))

    def prepare(self, **kwargs):
        self.save()
        return r.prepare(self.path, **kwargs)

    def test_rejects_audio_missing_from_final(self):
        del self.plan["scenes"][0]["audio"]
        with self.assertRaisesRegex(ValueError, "final requires"):
            self.prepare()
        self.prepare(silent_preview=True)

    def test_cjk_caption_wraps_without_inserting_spaces(self):
        text = '传统工艺，值得仔细观察。'
        lines = r.caption_lines(text, len, 8)
        self.assertEqual(''.join(lines), text)
        self.assertEqual(len(lines), 2)
        self.assertFalse(any(line.startswith(('，', '。')) for line in lines))

    def test_caption_wrap_never_silently_discards_overflow(self):
        with self.assertRaisesRegex(ValueError, 'overflows'):
            r.caption_lines('a very long text with too many words', len, 8)

    def test_custom_caption_size_rejects_unreadable_or_invalid_values(self):
        for value in (0, 8, True, float('nan'), 400):
            self.plan['captionSize'] = value
            with self.assertRaisesRegex(ValueError, 'captionSize'):
                self.prepare()

    def test_rejects_caption_overlaps_and_nan(self):
        self.plan["scenes"][0]["captions"][1]["start"] = .9
        with self.assertRaisesRegex(ValueError, "overlapping"):
            self.prepare()
        self.plan["scenes"][0]["captions"][1]["start"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.prepare()

    def test_rejects_path_escape_and_symlink(self):
        self.plan["scenes"][0]["visual"] = "../outside.png"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.prepare()
        (self.root / "outside-link").symlink_to(SCRIPT)
        self.plan["scenes"][0]["visual"] = "outside-link"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.prepare()

    def test_rejects_observed_without_evidence(self):
        self.plan["scenes"][0]["status"] = "observed"
        with self.assertRaisesRegex(ValueError, "observed requires"):
            self.prepare()

    def test_preview_receipt_and_no_overwrite(self):
        del self.plan["scenes"][0]["audio"]
        self.save()
        dest = self.root / "preview"
        r.render(self.path, dest, silent_preview=True)
        receipt = json.loads((dest / "evidence.json").read_text())
        self.assertTrue(receipt["preview"])
        self.assertEqual(receipt["frames"], 60)
        self.assertNotIn(str(self.root), (dest / "evidence.json").read_text())
        with self.assertRaisesRegex(ValueError, "already exists"):
            r.render(self.path, dest, silent_preview=True)

    def test_real_encode_clip_hold_and_audio(self):
        # A moving dot is editorial test content, not a claim about an app.
        frames = self.root / "motion"
        frames.mkdir()
        for n in range(30):
            image = self.image.copy()
            ImageDraw.Draw(image).ellipse((420+n*8, 220, 450+n*8, 250), fill="#cb4f39")
            image.save(frames / f"{n:03d}.png")
        r.command(["ffmpeg", "-v", "error", "-framerate", "30", "-i", frames / "%03d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p", self.root / "clip.mp4"])
        self.plan["scenes"].append({**self.plan["scenes"][0], "kind": "clip", "title": "Motion then a hold", "visual": "clip.mp4", "clipStart": 0, "clipEnd": 1})
        self.save()
        dest = self.root / "final"
        r.render(self.path, dest)
        receipt = json.loads((dest / "evidence.json").read_text())
        self.assertEqual(receipt["frames"], 120)
        self.assertEqual(receipt["checks"]["fullPlayback"], "pending")
        video = dest / "walkthrough.mp4"
        info = r.probe(video)
        self.assertEqual(next(s for s in info["streams"] if s["codec_type"] == "audio")["sample_rate"], "48000")
        self.assertAlmostEqual(float(info["format"]["duration"]), 4, delta=.08)
        def frame(t, name):
            target = self.root / name
            r.command(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video, "-frames:v", "1", target])
            return Image.open(target).convert("RGB").crop((0, 36, 640, 302))
        def mean_change(a, b):
            return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean)/3
        # Caption changes must not move/flash the visual body.
        self.assertLess(mean_change(frame(.4, "a.png"), frame(1.4, "b.png")), .15)
        # The same pipeline preserves a genuine visual change inside the action clip.
        self.assertGreater(mean_change(frame(2.1, "c.png"), frame(2.8, "d.png")), .3)
        # The clip's last frame holds rather than looping or stretching the action.
        self.assertLess(mean_change(frame(3.2, "e.png"), frame(3.7, "f.png")), .15)

    def test_rejects_silent_narration(self):
        with wave.open(str(self.root / "voice.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(48000)
            f.writeframes(b"\0\0" * 48000)
        with self.assertRaisesRegex(ValueError, "silent"):
            self.prepare()

    def test_rejects_invalid_clip_trim(self):
        s = self.plan["scenes"][0]
        s.update(kind="clip", visual="voice.wav", clipEnd=1)
        with self.assertRaisesRegex(ValueError, "visual has no"):
            self.prepare()

    def test_rejects_caption_overflow_at_render(self):
        self.plan["scenes"][0]["captions"][0]["text"] = "W" * 160
        self.save()
        with self.assertRaisesRegex(ValueError, "overflows"):
            r.render(self.path, self.root / "bad")
        self.assertFalse((self.root / "bad").exists())

    def test_portrait_clip_and_deliberate_crop_encode(self):
        r.command(['ffmpeg','-v','error','-loop','1','-i',self.root/'still.png','-t','1','-r','30','-c:v','libx264','-pix_fmt','yuv420p',self.root/'portrait-source.mp4'])
        self.plan.update(width=360,height=640)
        s=self.plan['scenes'][0]
        s.update(kind='clip',visual='portrait-source.mp4',clipStart=0,clipEnd=1,crop=[30,40,400,450],title='Voice')
        s['captions']=[dict(start=0,end=1,text='Pick a voice.'),dict(start=1,end=2,text='Keep it clear.')]
        self.save();dest=self.root/'portrait';r.render(self.path,dest)
        stream=next(x for x in r.probe(dest/'walkthrough.mp4')['streams'] if x['codec_type']=='video')
        self.assertEqual((stream['width'],stream['height']),(360,640))
        self.assertEqual(int(stream['nb_frames']),60)


if __name__ == "__main__":
    unittest.main()
