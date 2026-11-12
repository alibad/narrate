"""Behavioral checks using original synthetic fixtures; no browser or network."""
import importlib.util
import json
import math
import struct
import shutil
import subprocess
import sys
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
        self.path.write_text(json.dumps(self.plan), encoding="utf-8")

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

    def test_rejects_path_escape(self):
        self.plan["scenes"][0]["visual"] = "../outside.png"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.prepare()

    def test_rejects_symlink_escape(self):
        try:
            (self.root / "outside-link").symlink_to(SCRIPT)
        except OSError:
            self.skipTest("this account cannot create symlinks (Windows without Developer Mode)")
        self.plan["scenes"][0]["visual"] = "outside-link"
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.prepare()

    def test_utf8_plan_and_missing_default_glyphs_fail_clearly(self):
        # Pillow's built-in font has no é or em dash; that must stop the render, not draw boxes.
        self.plan["scenes"][0]["captions"][0]["text"] = "Un café — merci."
        with self.assertRaisesRegex(ValueError, "default font has no glyph for .*é"):
            self.prepare()
        self.plan["scenes"][0]["captions"][0]["text"] = "It’s “ready”."
        self.prepare()

    def test_right_to_left_and_complex_scripts_need_raqm(self):
        # A font with every glyph is not enough: without RAQM, Hebrew draws in the wrong order and Indic or Thai
        # letters don't join. Glyph coverage is taken as given here so only the shaping gate is under test.
        from unittest import mock
        with mock.patch.object(r, "missing_glyphs", return_value=[]), mock.patch("PIL.features.check", return_value=False):
            for text, script in [("שלום לכולם", "Hebrew"), ("مرحبا بكم", "Arabic"), ("नमस्ते", "Devanagari"), ("বাংলা", "Bengali"), ("வணக்கம்", "Tamil"), ("สวัสดี", "Thai")]:
                self.plan["scenes"][0]["captions"][0]["text"] = text
                with self.assertRaisesRegex(ValueError, f"{script} captions require Pillow RAQM"):
                    self.prepare()
            self.plan["scenes"][0]["captions"][0]["text"] = "Привет, 你好, Ελληνικά."
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
        receipt = json.loads((dest / "evidence.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["preview"])
        self.assertEqual(receipt["frames"], 60)
        self.assertNotIn(str(self.root), (dest / "evidence.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "already exists"):
            r.render(self.path, dest, silent_preview=True)

    def test_cli_summary_names_the_file_it_wrote(self):
        del self.plan["scenes"][0]["audio"]
        self.save()
        dest = self.root / "cli-preview"
        out = subprocess.run([sys.executable, str(SCRIPT), str(self.path), str(dest), "--silent-preview"], capture_output=True, text=True, check=True).stdout
        self.assertIn("silent preview", out)
        self.assertTrue(Path(out.split(" -> ", 1)[1].split(" (+", 1)[0]).is_file(), out)

    def test_real_encode_clip_hold_and_audio(self):
        # A moving dot is editorial test content, not a claim about an app.
        frames = self.root / "motion"
        frames.mkdir()
        for n in range(30):
            image = self.image.copy()
            ImageDraw.Draw(image).ellipse((420+n*8, 220, 450+n*8, 250), fill="#cb4f39")
            image.save(frames / f"{n:03d}.png")
        r.command(["ffmpeg", "-v", "error", "-framerate", "30", "-i", frames / "%03d.png", "-vf", "scale=out_range=full", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_range", "pc", self.root / "clip.mp4"])
        self.plan["scenes"].append({**self.plan["scenes"][0], "kind": "clip", "title": "Motion then a hold", "visual": "clip.mp4", "clipStart": 0, "clipEnd": 1})
        self.save()
        dest = self.root / "final"
        r.render(self.path, dest)
        receipt = json.loads((dest / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["frames"], 120)
        self.assertEqual(receipt["checks"]["fullPlayback"], "pending")
        video = dest / "walkthrough.mp4"
        info = r.probe(video)
        picture = next(s for s in info['streams'] if s['codec_type'] == 'video')
        self.assertEqual(picture['pix_fmt'], 'yuv420p')
        self.assertEqual(picture['color_range'], 'tv')
        self.assertEqual(picture['color_space'], 'bt709')
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

    def test_opt_in_look_keeps_exact_timing(self):
        # No header band, a chosen frame colour, a push-in on the first still and a crossfade into a red still.
        Image.new("RGB", (900, 500), "#cb4f39").save(self.root / "red.png")
        self.plan["scenes"].append({**self.plan["scenes"][0], "title": "A second hold", "visual": "red.png", "motion": "none"})
        self.plan.update(header=False, background="#1e1e1e", stillMotion="push", transition={"type": "crossfade", "seconds": .4})
        self.save()
        dest = self.root / "styled"
        r.render(self.path, dest)
        receipt = json.loads((dest / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["frames"], 120)
        self.assertEqual([s["motion"] for s in receipt["scenes"]], ["push", "none"])
        self.assertEqual(receipt["presentation"]["header"], False)
        frames = {}
        def frame(t):
            # Each time is extracted once: a second ffmpeg run onto the same file would stop at its overwrite prompt.
            if t not in frames:
                target = self.root / f"styled-{t}.png"
                r.command(["ffmpeg", "-v", "error", "-ss", str(t), "-i", dest / "walkthrough.mp4", "-frames:v", "1", target])
                frames[t] = Image.open(target).convert("RGB")
            return frames[t]
        def mean_change(a, b):
            return sum(ImageStat.Stat(ImageChops.difference(a.crop((0, 0, 640, 302)), b.crop((0, 0, 640, 302)))).mean)/3
        early = frame(.2)
        # Without the header the visual starts at the top; the pillarbox uses the chosen colour.
        self.assertGreater(sum(early.getpixel((320, 10))), 450)
        self.assertTrue(all(abs(v - 30) < 8 for v in early.getpixel((4, 150))))
        # The push-in moves the still; the plain red hold does not move.
        self.assertGreater(mean_change(early, frame(1.8)), .3)
        self.assertLess(mean_change(frame(2.6), frame(3.6)), .15)
        # Mid-crossfade is neither the outgoing hold nor the incoming still.
        middle = frame(2.2)
        self.assertGreater(mean_change(middle, frame(1.95)), .3)
        self.assertGreater(mean_change(middle, frame(2.6)), .3)

    def test_crossfade_keeps_captions_and_header_at_full_strength(self):
        # The second scene's first caption differs from the first scene's last one, and so does its title.
        Image.new("RGB", (900, 500), "#cb4f39").save(self.root / "red.png")
        self.plan["scenes"].append({**self.plan["scenes"][0], "title": "A second hold", "visual": "red.png"})
        self.plan["transition"] = {"type": "crossfade", "seconds": .4}
        self.save()
        dest = self.root / "faded"
        r.render(self.path, dest)
        def frame(t):
            target = self.root / f"faded-{t}.png"
            r.command(["ffmpeg", "-v", "error", "-ss", str(t), "-i", dest / "walkthrough.mp4", "-frames:v", "1", target])
            return Image.open(target).convert("RGB")
        def mean_change(a, b, box):
            return sum(ImageStat.Stat(ImageChops.difference(a.crop(box), b.crop(box))).mean)/3
        hhead, hfoot = r.zones(360)
        # Compare whole 16 px encoder blocks inside each band: a block that also holds the blending picture
        # carries a little of it after compression.
        header, caption = (0, 0, 640, hhead // 16 * 16), (0, -(-(360 - hfoot) // 16) * 16, 640, 360)
        picture = (0, hhead, 640, 360 - hfoot)
        inside, after, before = frame(2.1), frame(2.6), frame(1.9)
        # Inside the fade the bands already match the incoming scene; the picture is still blending.
        self.assertLess(mean_change(inside, after, caption), .15)
        self.assertLess(mean_change(inside, after, header), .15)
        self.assertGreater(mean_change(inside, before, caption), .3)
        self.assertGreater(mean_change(inside, after, picture), .3)
        self.assertGreater(mean_change(inside, before, picture), .3)

    def test_opt_in_look_is_validated(self):
        # A 1.35 s second scene (1 s of audio plus the hold) cannot take a 1 s crossfade.
        self.plan["scenes"].append({**self.plan["scenes"][0], "minDuration": 0, "captions": [{"start": 0, "end": 1, "text": "Short."}]})
        original = json.loads(json.dumps(self.plan))
        for key, value, message in [("background", "teal", "background"), ("header", "no", "header"), ("stillMotion", "zoom", "stillMotion"),
                                    ("transition", {"type": "wipe", "seconds": .4}, "transition"), ("transition", {"type": "crossfade", "seconds": 1}, "half the shortest")]:
            self.plan = json.loads(json.dumps(original))
            self.plan[key] = value
            with self.assertRaisesRegex(ValueError, message):
                self.prepare()
        self.plan = original
        self.plan["scenes"][0].update(kind="clip", visual="still.png", clipEnd=.04, motion="push")
        with self.assertRaisesRegex(ValueError, "on a still"):
            self.prepare()



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

    def frames_of(self, video):
        """frame(t) -> RGB image, each time extracted once (a second ffmpeg run onto one file would stop at a prompt)."""
        cache = {}
        def frame(t):
            if t not in cache:
                target = self.root / f"{video.parent.name}-{t}.png"
                r.command(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video, "-frames:v", "1", target])
                cache[t] = Image.open(target).convert("RGB")
            return cache[t]
        return frame

    def loudness(self, video, start, end):
        out = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(end - start), "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        return float(out.split("max_volume: ")[1].split(" dB")[0])

    def test_studio_options_are_validated(self):
        original = json.loads(json.dumps(self.plan))
        for key, value, message in [("captionStyle", "overlay", "captionStyle"), ("music", {"level": 2}, "music"), ("music", {"gain": .3}, "music"),
                                    ("music", {"level": True}, "music"), ("fade", {"in": 4}, "fade in"), ("fade", {"start": 1}, "fade"),
                                    ("fade", {}, "fade"), ("fade", {"out": 1.5}, "half its scene")]:
            self.plan = json.loads(json.dumps(original))
            self.plan[key] = value
            with self.assertRaisesRegex(ValueError, message):
                self.prepare()
        for scene, message in [({"camera": [{"t": 0, "cx": .5, "cy": .5, "z": 2}]}, "camera keys are for clips"),
                               ({"sounds": [{"at": 0, "effect": "boom"}]}, "click or whoosh"),
                               ({"sounds": [{"at": 0, "effect": ["click"]}]}, "click or whoosh"),
                               ({"sounds": [{"at": 2, "effect": "click"}]}, "inside its scene")]:
            self.plan = json.loads(json.dumps(original))
            self.plan["scenes"][0].update(scene)
            with self.assertRaisesRegex(ValueError, message):
                self.prepare()
        r.command(['ffmpeg', '-v', 'error', '-loop', '1', '-i', self.root / 'still.png', '-t', '1', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.root / 'held.mp4'])
        for keys in ([{"t": 0, "cx": .5, "cy": .5, "z": 4}], [{"t": 0, "cx": 1.2, "cy": .5, "z": 2}], [{"t": 1.5, "cx": .5, "cy": .5, "z": 2}],
                     [{"t": .6, "cx": .5, "cy": .5, "z": 2}, {"t": .3, "cx": .5, "cy": .5, "z": 1}], [{"t": 0, "x": .5, "cy": .5, "z": 2}], []):
            self.plan = json.loads(json.dumps(original))
            self.plan["scenes"][0].update(kind="clip", visual="held.mp4", clipEnd=1, camera=keys)
            with self.assertRaisesRegex(ValueError, "camera"):
                self.prepare()

    def test_camera_keys_on_a_cropped_clip_are_refused(self):
        # The keys frame the whole capture; on a cropped picture they would point at the wrong place.
        r.command(['ffmpeg', '-v', 'error', '-loop', '1', '-i', self.root / 'still.png', '-t', '1', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.root / 'held.mp4'])
        self.plan["scenes"][0].update(kind="clip", visual="held.mp4", clipEnd=1, crop=[0, 0, 450, 250], camera=[{"t": .2, "cx": .25, "cy": .5, "z": 2}])
        with self.assertRaisesRegex(ValueError, "cannot also be cropped"):
            self.prepare()
        del self.plan["scenes"][0]["camera"]
        self.prepare()

    def test_music_bed_covers_the_longest_plan(self):
        # 40 scenes of 90 s is 3600 s; the bed asked for half a second more, which soundbed.py refuses.
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import soundbed
        finally:
            sys.path.remove(str(SCRIPT.parent))
        with self.assertRaisesRegex(ValueError, "bed length"):
            soundbed.bed(40 * 90 + .5, self.root / "x.wav")
        self.assertEqual(r.bed_length(40 * 90), 3600)
        self.assertEqual(r.bed_length(10), 10.5)

    def test_filter_graph_goes_to_ffmpeg_as_a_file(self):
        # One clip with 40 camera keys makes a graph over 100 KB: more than Linux takes in one argument.
        r.command(['ffmpeg', '-v', 'error', '-loop', '1', '-i', self.root / 'still.png', '-t', '2', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.root / 'held.mp4'])
        keys = [{"t": round(k * .05, 2), "cx": .25 + .5 * (k % 2), "cy": .5, "z": 1 + k % 3} for k in range(40)]
        self.plan["scenes"][0].update(kind="clip", visual="held.mp4", clipEnd=2, camera=keys)
        self.save()
        calls, run = [], r.command
        def spy(args):
            calls.append([str(a) for a in args])
            if graph_option in calls[-1]:
                graph = Path(calls[-1][calls[-1].index(graph_option) + 1])
                calls[-1].append(f"graph of {len(graph.read_text(encoding='utf-8'))} characters")
            return run(args)
        graph_option = r.graph_option()
        r.command = spy
        try:
            r.render(self.path, self.root / "long-graph")
        finally:
            r.command = run
        encode = next(c for c in calls if graph_option in c)
        self.assertGreater(int(encode[-1].split()[2]), 100_000)
        self.assertLess(max(len(a) for c in calls for a in c), 4096)
        self.assertTrue((self.root / "long-graph" / "walkthrough.mp4").is_file())

    def test_graph_option_is_tried_not_read_from_the_version(self):
        # FFmpeg 6 refuses -/filter_complex, also as a git build whose version reads N-<commit>; 7 and later take it.
        run = r.subprocess.run
        try:
            for refused, expected in ((True, "-filter_complex_script"), (False, "-/filter_complex")):
                r.graph_option.cache_clear()
                r.subprocess.run = lambda args, **kw: subprocess.CompletedProcess(args, 8 if refused and "-/filter_complex" in args else 0, "", "")
                self.assertEqual(r.graph_option(), expected)
        finally:
            r.subprocess.run = run
            r.graph_option.cache_clear()
        # The real FFmpeg here takes the option it is given.
        self.assertIn(r.graph_option(), ("-/filter_complex", "-filter_complex_script"))

    def test_camera_moves_wait_for_the_last_to_land(self):
        z, x, y = r.camera_expressions([{"t": .1, "cx": .25, "cy": .5, "z": 2}, {"t": .5, "cx": .5, "cy": .5, "z": 1}], 30)
        # The second move was asked for at 0.5 s, before the first landed at 1.0 s, so it starts at 1.0 s.
        self.assertIn("lt((on/30),0.100)", z)
        self.assertIn("lt((on/30),1.000)", z)
        self.assertNotIn("0.500", z)
        self.assertIn(f"W-W/({z})", x)
        # cy never changes, so the framed area stays centred vertically for whatever zoom.
        self.assertEqual(y, f"clip((0.5)*H-H/({z})/2,0,H-H/({z}))")

    def test_camera_on_a_clip_is_editorial_and_keeps_timing(self):
        # A held picture as a clip: only the camera can change it.
        r.command(['ffmpeg', '-v', 'error', '-loop', '1', '-i', self.root / 'still.png', '-t', '2', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.root / 'held.mp4'])
        self.plan["scenes"][0].update(kind="clip", visual="held.mp4", clipEnd=2, minDuration=2.5, camera=[{"t": .2, "cx": .25, "cy": .5, "z": 2}])
        self.save()
        dest = self.root / "camera"
        r.render(self.path, dest)
        receipt = json.loads((dest / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["frames"], 75)
        self.assertEqual(receipt["scenes"][0]["motion"], "camera")
        self.assertEqual(receipt["scenes"][0]["camera"], [{"t": .2, "cx": .25, "cy": .5, "z": 2}])
        frame = self.frames_of(dest / "walkthrough.mp4")
        def mean_change(a, b):
            return sum(ImageStat.Stat(ImageChops.difference(a.crop((0, 36, 640, 302)), b.crop((0, 36, 640, 302)))).mean)/3
        self.assertLess(mean_change(frame(0), frame(.15)), .15)  # wide until the key
        self.assertGreater(mean_change(frame(.15), frame(1.5)), 3)  # pushed in on the dark left half
        self.assertLess(mean_change(frame(1.5), frame(2.3)), .15)  # landed, and the clip's last frame holds zoomed

    def edge_steps(self, video):
        """How far a white block's left edge moves from each frame to the next, to a fraction of a pixel: on row 150,
        the edge sits where the light starts in a window from x 60 to 130."""
        frames = self.root / f"{video.parent.name}-frames"
        frames.mkdir()
        r.command(["ffmpeg", "-v", "error", "-i", video, "-fps_mode", "passthrough", frames / "%03d.png"])
        edges = []
        for path in sorted(frames.glob("*.png")):
            with Image.open(path) as im:
                grey = im.convert("L")
                edges.append(130 - sum(grey.getpixel((x, 150)) for x in range(60, 130)) / 255)
        return [b - a for a, b in zip(edges, edges[1:])]

    def test_camera_and_push_glide_without_stepping_back(self):
        # A white block whose left edge lands at x 100 of the 640 x 302 picture (no header, a caption band below).
        block = Image.new("RGB", (1280, 604), "black")
        ImageDraw.Draw(block).rectangle((200, 100, 519, 499), fill="white")
        block.save(self.root / "block.png")
        self.plan.update(header=False, stillMotion="push")
        self.plan["scenes"][0]["visual"] = "block.png"
        self.save()
        r.render(self.path, self.root / "push")
        steps = self.edge_steps(self.root / "push" / "walkthrough.mp4")
        # A 5% push over 2 s moves the edge left about 0.18 px a frame, never back. zoompan framed whole pixels and
        # stepped the edge back and forth, by up to half a pixel on alternate frames: shimmer. (The encoder may hold
        # one frame and catch up on the next, so the steps are not all equal.)
        self.assertEqual(len(steps), 59)
        self.assertLess(max(steps), .05, steps)
        self.assertAlmostEqual(sum(steps), -220 * .05 * 59 / 60, delta=1, msg=steps)
        self.assertAlmostEqual(sorted(steps)[29], -.18, delta=.04, msg=steps)
        # A camera move on a clip eases over 0.9 s: the edge only ever moves one way, and it is still at both ends.
        r.command(['ffmpeg', '-v', 'error', '-loop', '1', '-i', self.root / 'block.png', '-t', '2', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.root / 'block.mp4'])
        self.plan.pop("stillMotion")
        self.plan["scenes"][0].update(kind="clip", visual="block.mp4", clipEnd=2, camera=[{"t": .3, "cx": .5, "cy": .5, "z": 1.1}])
        self.save()
        r.render(self.path, self.root / "camera-move")
        steps = self.edge_steps(self.root / "camera-move" / "walkthrough.mp4")
        moving = steps[9:36]
        self.assertLess(max(moving), .05, moving)
        self.assertLess(min(moving), -1, moving)
        self.assertAlmostEqual(sum(steps), -220 * .1, delta=1, msg=steps)
        self.assertLess(max(map(abs, steps[:8] + steps[38:])), .05, steps)

    def test_lower_third_captions_sit_over_the_picture_at_full_strength(self):
        Image.new("RGB", (900, 500), "#edf1f5").save(self.root / "light.png")
        scene = {**self.plan["scenes"][0], "visual": "light.png", "captions": [{"start": 0, "end": 1, "text": "A synthetic test fixture."}]}
        self.plan.update(captionStyle="lowerThird", transition={"type": "crossfade", "seconds": .4},
                         scenes=[scene, {**scene, "title": "A second hold", "captions": [{"start": 0, "end": 1, "text": "The second card."}]}])
        self.save()
        dest = self.root / "lower"
        r.render(self.path, dest)
        self.assertIn("00:00:02,000 --> 00:00:03,000\nThe second card.", (dest / "captions.srt").read_text(encoding="utf-8"))
        frame = self.frames_of(dest / "walkthrough.mp4")
        surface = (247, 245, 239)
        def near(pixel, colour, tolerance=12):
            return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour))
        # No caption band: the picture reaches the bottom of the frame.
        self.assertTrue(near(frame(1.5).getpixel((600, 352)), (237, 241, 245)))
        # The card is over the picture while its caption runs, and gone after it.
        self.assertTrue(near(frame(.5).getpixel((44, 312)), surface))
        self.assertTrue(near(frame(1.5).getpixel((44, 312)), (237, 241, 245)))
        # Inside the crossfade the picture blends, but the next card is already solid on the scene's first frames.
        self.assertTrue(near(frame(2.1).getpixel((44, 312)), surface))

    def test_music_bed_sound_effects_and_fades(self):
        del self.plan["scenes"][0]["audio"]
        self.plan["scenes"][0]["sounds"] = [{"at": 1, "effect": "whoosh"}]
        self.save()
        dest = self.root / "effects"
        r.render(self.path, dest, silent_preview=True)
        video = dest / "silent-preview.mp4"
        # Without music the film is silent until the whoosh starts at 1 s.
        self.assertLess(self.loudness(video, 0, .9), -70)
        self.assertGreater(self.loudness(video, 1, 1.6), -40)
        receipt = json.loads((dest / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["presentation"]["soundEffects"], "generated by scripts/sfx.py")
        self.plan.update(music={"level": .5}, fade={"in": .5, "out": .5})
        self.save()
        dest = self.root / "bed"
        r.render(self.path, dest, silent_preview=True)
        video = dest / "silent-preview.mp4"
        self.assertEqual(json.loads((dest / "evidence.json").read_text(encoding="utf-8"))["frames"], 60)
        self.assertGreater(self.loudness(video, .6, .9), -45)
        frame = self.frames_of(video)
        # The film opens from and closes to the frame colour.
        self.assertTrue(all(abs(a - b) < 8 for a, b in zip(frame(0).getpixel((320, 180)), (16, 24, 32))))
        self.assertTrue(all(abs(a - b) < 8 for a, b in zip(frame(1).getpixel((500, 150)), (237, 241, 245))))

    def band_level(self, video, start, end):
        # The bed's low pad and pulse, below the 440 Hz test narration: three low-pass stages leave the tone ~55 dB down.
        out = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(end - start), "-i", str(video), "-af",
                              "lowpass=f=150,lowpass=f=150,lowpass=f=150,volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        return float(out.split("mean_volume: ")[1].split(" dB")[0])

    def test_empty_music_option_plays_the_default_bed(self):
        del self.plan["scenes"][0]["audio"]
        self.plan["music"] = {}
        self.save()
        dest = self.root / "default-bed"
        r.render(self.path, dest, silent_preview=True)
        self.assertEqual(json.loads((dest / "evidence.json").read_text(encoding="utf-8"))["presentation"]["music"], {"level": .3})
        self.assertGreater(self.loudness(dest / "silent-preview.mp4", .8, 1.6), -50)

    def test_music_ducks_under_the_narrator(self):
        # Narration that pauses, speaks, then pauses: the bed must drop while the voice speaks and come back after.
        with wave.open(str(self.root / "paused.wav"), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(48000)
            f.writeframes(b"\0\0" * 3 * 48000 + b"".join(struct.pack("<h", round(5000*math.sin(2*math.pi*440*n/48000))) for n in range(3 * 48000)) + b"\0\0" * 4 * 48000)
        self.plan["scenes"][0].update(audio="paused.wav", minDuration=10, captions=[{"start": 3, "end": 6, "text": "A synthetic test fixture."}])
        self.plan["music"] = {"level": .5}
        self.save()
        dest = self.root / "ducked"
        r.render(self.path, dest)
        video = dest / "walkthrough.mp4"
        speaking, after = self.band_level(video, 4, 5.8), self.band_level(video, 6.6, 7.4)
        self.assertGreater(after - speaking, 6, f"bed {speaking} dB under the voice, {after} dB after it")

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
