#!/usr/bin/env python3
"""Offline, frame-counted walkthrough assembly. No network or capture driver."""
from __future__ import annotations
import argparse
import functools
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path


PUSH = .05  # a still's optional push-in grows by 5% over its scene
MOVE = .9  # seconds an editorial camera move on a clip takes, eased in and out
SOUNDBED = Path(__file__).resolve().parent / "soundbed.py"
SFX = Path(__file__).resolve().parent / "sfx.py"
EFFECTS = {"click": .5, "whoosh": .28}  # mix level of each effect sfx.py makes
LONGEST_BED = 3600  # seconds, soundbed.py's longest bed, as long as the longest plan (40 scenes of 90 s)
DEFAULT_COLOURS = {"status": "#85d4c5", "title": "#ffffff", "caption": "#ffffff"}
LOWER_THIRD = {"surface": "#f7f5ef", "text": "#161b24", "accent": "#ed503d"}




def seconds_option(value, label, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
        raise ValueError(f"{label} must be 0 to {upper} seconds")
    return value


def camera_keys(keys, span, scene):
    """Validated editorial camera keys for a clip: [{t, cx, cy, z}], t in scene seconds within the clip, the centre as a
    share of the picture, z from 1 (the whole picture) to 3."""
    if not isinstance(keys, list) or not 1 <= len(keys) <= 40:
        raise ValueError(f"Scene {scene}: camera takes 1 to 40 keys")
    previous = 0
    for k in keys:
        if not isinstance(k, dict) or set(k) != {"t", "cx", "cy", "z"}:
            raise ValueError(f"Scene {scene}: each camera key is {{t, cx, cy, z}}")
        t, cx, cy, z = (number(k[p], f"camera {p}") for p in ("t", "cx", "cy", "z"))
        if not previous <= t <= span or cx > 1 or cy > 1 or not 1 <= z <= 3:
            raise ValueError(f"Scene {scene}: camera keys need ascending t within the clip, cx and cy from 0 to 1 and z from 1 to 3")
        previous = t
    return keys


def camera_expressions(keys, fps):
    """The zoom and the top-left corner of what the camera frames, as expressions of the output frame `on` and the
    source size `W` x `H`, for frame_view. Each move eases (smoothstep) over MOVE seconds from where the last one
    landed; a move asked for before the last one has landed waits for it."""
    clock = f"(on/{fps})"
    state, landed = {"z": 1, "cx": .5, "cy": .5}, -math.inf
    ex = {"z": "1", "cx": "0.5", "cy": "0.5"}
    for k in keys:
        t0 = max(k["t"], landed + MOVE)
        landed = t0
        u = f"clip(({clock}-{t0:.3f})/{MOVE},0,1)"
        for p in ex:
            a, b = f"{state[p]:.4f}", f"{k[p]:.4f}"
            if a != b:
                ex[p] = f"if(lt({clock},{t0:.3f}),{ex[p]},{a}+({b}-{a})*({u}*{u}*(3-2*{u})))"
        state = {p: k[p] for p in state}
    z = ex["z"]
    return z, f"clip(({ex['cx']})*W-W/({z})/2,0,W-W/({z}))", f"clip(({ex['cy']})*H-H/({z})/2,0,H-H/({z}))"


def frame_view(z, x, y):
    """A filter that frames W/z x H/z of the source from (x, y) and fills the frame with it, to a fraction of a
    pixel, with cubic interpolation. zoompan snaps the framed area to whole pixels, so a slow move shimmered: text
    stepped back and forth by up to half a pixel on alternate frames (measured 10 Nov 2026)."""
    x1, y1 = f"{x}+W/({z})", f"{y}+H/({z})"
    return f"perspective=x0='{x}':y0='{y}':x1='{x1}':y1='{y}':x2='{x}':y2='{y1}':x3='{x1}':y3='{y1}':interpolation=cubic:eval=frame"


def sound_cues(sounds, duration, scene):
    if not isinstance(sounds, list) or len(sounds) > 60:
        raise ValueError(f"Scene {scene}: sounds is a list of at most 60 cues")
    for cue in sounds:
        if not isinstance(cue, dict) or set(cue) != {"at", "effect"} or not isinstance(cue["effect"], str) or cue["effect"] not in EFFECTS:
            raise ValueError(f"Scene {scene}: each sound is {{at, effect}} with effect {' or '.join(EFFECTS)}")
        if not number(cue["at"], "sound at") < duration:
            raise ValueError(f"Scene {scene}: a sound starts inside its scene")
    return sounds


def bed_length(seconds):
    """The music bed runs half a second past the film, so it never ends first, within soundbed.py's longest bed."""
    return min(seconds + .5, LONGEST_BED)


@functools.cache
def graph_option():
    """How this FFmpeg reads a filter graph from a file. A camera plan's graph can pass 1 MB (138 KB for one scene of
    40 keys), more than a command line takes: macOS allows about 1 MB in all, Linux 128 KB an argument. FFmpeg 7 reads
    the file with -/filter_complex and deprecates -filter_complex_script, the only way in FFmpeg 6. Tried rather than
    read from the version, which a git build gives as N-<commit>."""
    with tempfile.TemporaryDirectory(prefix="narrate-video-graph-") as work:
        graph = Path(work) / "graph.txt"
        graph.write_text("anullsrc,atrim=end_sample=1[a]", encoding="utf-8")
        tried = subprocess.run(["ffmpeg", "-v", "error", "-/filter_complex", str(graph), "-map", "[a]", "-f", "null", "-"],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return "-/filter_complex" if tried.returncode == 0 else "-filter_complex_script"


def command(args):
    # No keyboard input: an ffmpeg prompt (such as "Overwrite? [y/N]") fails at once instead of waiting forever.
    result = subprocess.run([str(a) for a in args], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ValueError(f"{Path(str(args[0])).name} failed: {result.stderr[-1800:]}")
    return result.stdout


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def audio_peak(path):
    check = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "-"], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace")
    peak = re.search(r"max_volume: (-?(?:[0-9.]+|inf)) dB", check.stderr)
    if check.returncode or not peak:
        raise ValueError("Could not measure narration audio")
    return float(peak.group(1))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def number(value, label, lower=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < lower:
        raise ValueError(f"{label} must be a finite number >= {lower}")
    return value


def asset(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("Asset paths must be relative to the plan")
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Missing asset or path escapes the plan directory")
    return path


def prepare(plan_path, silent_preview=False):
    root = plan_path.resolve().parent
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("version") != 1:
        raise ValueError("Expected plan version 1")
    width, height, fps = plan.get("width", 1920), plan.get("height", 1080), plan.get("fps", 30)
    if fps not in (24, 30, 60) or isinstance(fps, bool):
        raise ValueError("fps must be 24, 30 or 60")
    for value in (width, height):
        if type(value) is not int or value % 2 or not 360 <= value <= 3840:
            raise ValueError("Dimensions must be even integers from 360 to 3840")
    if not .5 <= width / height <= 2:
        raise ValueError("Use landscape or portrait aspect ratio between .5 and 2")
    if 'captionSize' in plan:
        value = plan['captionSize']
        if type(value) is not int or not 16 <= value <= max(16, round(height*.06)):
            raise ValueError('captionSize must be a readable integer within the caption zone')
    plan["_colours"] = dict(DEFAULT_COLOURS)
    plan["_lowerThird"] = dict(LOWER_THIRD)
    if plan.get("captionStyle", "band") not in ("band", "lowerThird"):
        raise ValueError('captionStyle must be "band" or "lowerThird"')
    music = plan.get("music")
    if music is not None:
        level = music.get("level", .3) if isinstance(music, dict) else None
        if not isinstance(music, dict) or set(music) - {"level"} or isinstance(level, bool) or not isinstance(level, (int, float)) or not .05 <= level <= 1:
            raise ValueError('music must be {"level": 0.05 to 1}')
    fade = plan.get("fade")
    if fade is not None:
        if not isinstance(fade, dict) or not fade or set(fade) - {"in", "out"}:
            raise ValueError('fade must be {"in": seconds, "out": seconds}')
        for key in fade:
            seconds_option(fade[key], f"fade {key}", 3)
    background = plan.get("background", "#101820")
    if not isinstance(background, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
        raise ValueError('background must be a "#rrggbb" colour')
    if not isinstance(plan.get("header", True), bool):
        raise ValueError("header must be true or false")
    transition = plan.get("transition")
    if transition is not None and (not isinstance(transition, dict) or transition.get("type") != "crossfade" or isinstance(transition.get("seconds"), bool)
                                   or not isinstance(transition.get("seconds"), (int, float)) or not .1 <= transition["seconds"] <= 1):
        raise ValueError('transition must be {"type": "crossfade", "seconds": 0.1 to 1}')
    still_motion = plan.get("stillMotion", "none")
    if still_motion not in ("none", "push"):
        raise ValueError('stillMotion must be "none" or "push"')
    font = asset(root, plan["font"]) if plan.get("font") else None
    voice = plan.get('voice', {})
    if not silent_preview and not all(isinstance(voice.get(k), str) and voice[k].strip() for k in ('provider','model','revision','name','language')):
        raise ValueError('Final requires explicit voice provider, model, revision, name and language')
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 40:
        raise ValueError("Provide 1 to 40 scenes")
    prepared = []
    for i, s in enumerate(scenes, 1):
        if s.get("kind") not in ("still", "clip"):
            raise ValueError(f"Scene {i}: kind must be still or clip")
        motion = s.get("motion", still_motion if s["kind"] == "still" else "none")
        if motion not in ("none", "push") or (motion == "push" and s["kind"] != "still"):
            raise ValueError(f'Scene {i}: motion is "none", or "push" on a still; a clip keeps its own movement')
        status = s.get("status")
        if status not in ("observed", "demonstration", "editorial"):
            raise ValueError(f"Scene {i}: label the evidence status")
        evidence = s.get("evidence", {})
        required = ("capturedAt", "surface", "target", "action", "build")
        if status == "observed" and not all(isinstance(evidence.get(k), str) and evidence[k].strip() for k in required):
            raise ValueError(f"Scene {i}: observed requires capture time, surface, target, action and build (unknown allowed)")
        visual = asset(root, s.get("visual"))
        info = probe(visual)
        if not any(x["codec_type"] == "video" for x in info["streams"]):
            raise ValueError(f"Scene {i}: visual has no video/image stream")
        crop = s.get('crop')
        if crop is not None:
            vs = next(x for x in info['streams'] if x['codec_type']=='video')
            if (not isinstance(crop,list) or len(crop)!=4 or any(type(v) is not int for v in crop)
                    or not (0 <= crop[0] < crop[2] <= vs['width'] and 0 <= crop[1] < crop[3] <= vs['height'])):
                raise ValueError(f'Scene {i}: invalid deliberate crop')
        audio = asset(root, s["audio"]) if s.get("audio") else None
        say = s.get("say", "")
        if not isinstance(say, str) or len(say) > 800:
            raise ValueError(f"Scene {i}: keep narration within 800 characters")
        if not silent_preview and (not audio or not say.strip()):
            raise ValueError(f"Scene {i}: final requires narration text and an audio file")
        audio_duration = 0
        if audio:
            ai = probe(audio)
            if not any(x["codec_type"] == "audio" for x in ai["streams"]):
                raise ValueError(f"Scene {i}: narration has no audio stream")
            audio_duration = number(float(ai["format"]["duration"]), "audio duration", .05)
            if audio_peak(audio) < -55:
                raise ValueError(f"Scene {i}: narration is silent or below -55 dBFS peak")
        start, end = 0, 0
        if s["kind"] == "clip":
            start = number(s.get("clipStart", 0), "clipStart")
            end = number(s.get("clipEnd"), "clipEnd", .05)
            if not start < end <= float(info["format"]["duration"]) + .001:
                raise ValueError(f"Scene {i}: invalid clip trim")
        duration = max(number(s.get("minDuration", 0), "minDuration"), audio_duration + .35, end - start)
        if not .5 <= duration <= 90:
            raise ValueError(f"Scene {i}: duration must be .5 to 90 seconds")
        frames = math.ceil(duration * fps - 1e-8)
        duration = frames / fps
        camera = s.get("camera")
        if camera is not None:
            if s["kind"] != "clip":
                raise ValueError(f'Scene {i}: camera keys are for clips; a still uses motion "push"')
            if crop:
                # The keys frame the whole capture (studio.focus measures the full viewport), so on a cropped picture
                # they would point at the wrong place. The camera can frame the same detail instead of the crop.
                raise ValueError(f"Scene {i}: a clip with camera keys cannot also be cropped; frame it with the camera instead")
            camera = camera_keys(camera, end - start, i)
        sounds = sound_cues(s.get("sounds", []), duration, i)
        captions = s.get("captions", [])
        previous_end = 0
        if not isinstance(captions, list) or (say.strip() and not captions):
            raise ValueError(f"Scene {i}: supply explicit caption timings")
        for c in captions:
            cs, ce = number(c.get("start"), "caption start"), number(c.get("end"), "caption end")
            if cs < previous_end or not cs < ce <= duration:
                raise ValueError(f"Scene {i}: overlapping or out-of-range captions")
            if round(cs*fps) >= round(ce*fps):
                raise ValueError(f'Scene {i}: caption shorter than one output frame')
            if not isinstance(c.get("text"), str) or not c["text"].strip() or len(c["text"]) > 180:
                raise ValueError(f"Scene {i}: caption must have 1 to 180 characters")
            previous_end = ce
        title = s.get("title", f"Scene {i}")
        if not isinstance(title, str) or not 1 <= len(title) <= 90:
            raise ValueError(f"Scene {i}: title must have 1 to 90 characters")
        missing = missing_glyphs(title + "".join(c["text"] for c in captions), font)
        if missing:
            raise ValueError(f"Scene {i}: the {'supplied' if font else 'default'} font has no glyph for {' '.join(missing[:8])}; "
                             "set \"font\" to a suitably licensed font that covers this text and inspect shaping in the result")
        script = needs_shaping(title + ''.join(c['text'] for c in captions))
        if script:
            from PIL import features
            if not features.check('raqm'):
                raise ValueError(f'Scene {i}: {script} captions require Pillow RAQM shaping support; without it they draw '
                                 'in the wrong order or with broken letters. Install libraqm and reinstall Pillow')
        prepared.append(dict(source={**s, "title": title}, visual=visual, audio=audio, seconds=duration, frames=frames, clipStart=start, clipEnd=end,
                             motion="camera" if camera else motion, camera=camera, sounds=sounds))
    if transition and len(prepared) > 1 and transition["seconds"] > min(p["seconds"] for p in prepared) / 2:
        raise ValueError("transition is longer than half the shortest scene")
    if fade and (fade.get("in", 0) > prepared[0]["seconds"] / 2 or fade.get("out", 0) > prepared[-1]["seconds"] / 2):
        raise ValueError("a fade is longer than half its scene")
    return plan, prepared, font


def subtitle_time(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


@functools.lru_cache(maxsize=8)
def _glyph_probe(font_path):
    from PIL import ImageFont
    font = ImageFont.truetype(str(font_path), 32) if font_path else ImageFont.load_default(size=32)
    def shape(ch):
        mask = font.getmask(ch)
        return mask.size, bytes(mask)
    return shape, shape("￿")


# Scripts Pillow's basic layout draws wrongly. Right to left: Hebrew, Arabic, Syriac, Thaana, N'Ko and the rest
# of U+0590–U+08FF, plus their presentation forms. Complex shaping: the Indic scripts and Sinhala (U+0900–U+0DFF),
# Thai, Lao, Tibetan, Myanmar and Khmer. Each needs RAQM (HarfBuzz and FriBiDi) to reorder and join its letters.
RTL_RANGES = ((0x0590, 0x08FF), (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF))
SHAPED_RANGES = RTL_RANGES + ((0x0900, 0x0DFF), (0x0E00, 0x0FFF), (0x1000, 0x109F), (0x1780, 0x17FF), (0xA8E0, 0xA8FF))


def _in(c, ranges):
    return any(a <= ord(c) <= b for a, b in ranges)


def needs_shaping(text):
    """The name of the first script in `text` that needs RAQM (e.g. "Hebrew", "Devanagari"), or None."""
    c = next((c for c in text if _in(c, SHAPED_RANGES)), None)
    if c is None:
        return None
    name = unicodedata.name(c, "complex-script").split()[0]
    return name.title()


def missing_glyphs(text, font_path):
    """Characters the font would draw as its missing-glyph box. Pillow's default font lacks even é and —."""
    shape, notdef = _glyph_probe(font_path)
    # Combining marks and format characters are drawn with their base; they cannot be judged alone.
    return sorted({ch for ch in text if not ch.isspace() and unicodedata.category(ch)[0] not in "MC" and shape(ch) == notdef})


def caption_lines(text, measure, max_width):
    import re
    cjk = any('\u2e80' <= c <= '\u9fff' for c in text)
    # CJK normally has no inter-word spaces. Keep closing punctuation with its base.
    words = re.findall(r'.[，。！？；：、）》」』]*', text) if cjk else text.split()
    joiner = '' if cjk else ' '
    lines, line = [], ''
    for word in words:
        trial = (line + joiner + word).strip()
        if measure(trial) > max_width:
            if not line or measure(word) > max_width:
                raise ValueError('Caption word overflows')
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    if len(lines) > 2:
        raise ValueError('Caption overflows; split into shorter timed cues')
    return lines


def zones(height, header=True, caption_style="band"):
    """Header and caption bands sit outside the visual, so neither ever covers it. Lower-third captions have no band:
    they sit over the bottom of the picture instead."""
    return (2*round(height * .1/2) if header else 0), (0 if caption_style == "lowerThird" else 2*round(height * .16/2))


def lower_third(path, text, width, height, font_path, caption_size=None, colours=None):
    """A caption as a card over the bottom of the picture, as a transparent full-frame overlay: a surface card with an
    accent bar on its reading edge and a soft shadow, at the left (the right for right-to-left text). Empty text
    writes a clear frame. Laid over the finished picture, so a camera move never moves it."""
    from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont
    colours = colours or LOWER_THIRD
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if text:
        size = caption_size or max(16, round(height * .032))
        font = ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)
        measure = ImageDraw.Draw(canvas)
        bar, pad_x, pad_y, line = max(4, round(size * .26)), round(size * .8), round(size * .55), round(size * 1.32)
        lines = caption_lines(text, lambda value: measure.textlength(value, font=font), round(width * .62) - bar - 2 * pad_x)
        first = next((c for c in text if _in(c, RTL_RANGES)), None)
        lang = {'HEBREW': 'he', 'ARABIC': 'ar'}.get(unicodedata.name(first, ' ').split()[0]) if first else None
        rtl = {'direction': 'rtl', **({'language': lang} if lang else {})} if first else {}
        w = bar + 2 * pad_x + math.ceil(max(measure.textlength(value, font=font, **rtl) for value in lines))
        h = 2 * pad_y + line * len(lines)
        x0 = width - round(width * .05) - w if first else round(width * .05)
        y0 = height - round(height * .08) - h
        radius = round(size * .45)
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + size * .35, x0 + w, y0 + h + size * .35), radius, fill=(0, 0, 0, 90))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(size * .5)))
        card = Image.new("RGBA", (w, h), ImageColor.getrgb(colours["surface"]) + (255,))
        draw = ImageDraw.Draw(card)
        draw.rectangle((w - bar, 0, w, h) if first else (0, 0, bar - 1, h), fill=colours["accent"])
        for k, value in enumerate(lines):
            y = pad_y + line * (k + .5)
            draw.text((w - bar - pad_x, y) if first else (bar + pad_x, y), value, font=font, fill=colours["text"], anchor="rm" if first else "lm", **rtl)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
        canvas.paste(card, (x0, y0), mask)
    canvas.save(path)


def plate(path, scene, text, width, height, font_path, caption_size=None, header=True, background="#101820", colours=None, caption_style="band"):
    colours = colours or DEFAULT_COLOURS
    from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
    hhead, hfoot = zones(height, header, caption_style)
    canvas = Image.new("RGBA", (width, height), ImageColor.getrgb(background) + (255,))
    if scene["source"]["kind"] == "still" and scene["motion"] == "none":
        with Image.open(scene["visual"]) as raw:
            shot = ImageOps.exif_transpose(raw).convert("RGBA")
            if scene['source'].get('crop'): shot = shot.crop(scene['source']['crop'])
            shot = ImageOps.contain(shot, (width, height - hhead - hfoot))
            canvas.alpha_composite(shot, ((width - shot.width) // 2, hhead + (height - hhead - hfoot - shot.height) // 2))
    else:
        ImageDraw.Draw(canvas).rectangle((0, hhead, width, height - hfoot - 1), fill=(0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    # A separate portrait composition keeps captions and focused UI legible on phones.
    size = caption_size or max(16, round(min(width*.055, height*.060)))
    font = ImageFont.truetype(str(font_path), size) if font_path else ImageFont.load_default(size=size)
    margin = round(width * .025)
    if header:
        titlesize = max(12, round(min(size*.85, hhead*.32)))
        titlefont = ImageFont.truetype(str(font_path), titlesize) if font_path else ImageFont.load_default(size=titlesize)
        title = scene["source"]["title"]
        status = scene["source"]["status"].upper()
        label = title
        if draw.textlength(label, font=titlefont) > width - 2 * margin:
            raise ValueError("Header overflows; shorten the scene title")
        draw.text((margin, max(6, hhead*.15)), status, font=titlefont, fill=colours["status"])
        draw.text((margin, max(6, hhead*.53)), label, font=titlefont, fill=colours["title"])
    lines = caption_lines(text, lambda value: draw.textlength(value, font=font), width - 2*margin)
    y = height - hfoot + (hfoot - len(lines) * size * 1.25) / 2
    for line in lines:
        first = next((c for c in line if _in(c, RTL_RANGES)), None)
        lang = {'HEBREW': 'he', 'ARABIC': 'ar'}.get(unicodedata.name(first, ' ').split()[0]) if first else None
        rtl = {'direction': 'rtl', **({'language': lang} if lang else {})} if first else {}
        draw.text(((width - draw.textlength(line, font=font)) / 2, y), line, font=font, fill=colours["caption"], **rtl)
        y += size * 1.25
    canvas.save(path)


def render(plan_path, destination, silent_preview=False):
    plan, scenes, font = prepare(plan_path, silent_preview)
    if destination.exists():
        raise ValueError("Output directory already exists; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = plan.get("width", 1920), plan.get("height", 1080), plan.get("fps", 30)
    header, background = plan.get("header", True), plan.get("background", "#101820")
    caption_style = plan.get("captionStyle", "band")
    hhead, hfoot = zones(height, header, caption_style)
    body, fill = height - hhead - hfoot, "0x" + background[1:]
    total = sum(s["frames"] for s in scenes)
    with tempfile.TemporaryDirectory(prefix="narrate-video-", dir=destination.parent) as workdir:
        work = Path(workdir)
        inputs, filters, concat, srt, receipt = [], [], [], [], []
        cards, effects = [], []  # lower-third captions and sound effects, on the film's frame clock
        clock, input_index, frame_clock = 0, 0, 0
        for i, s in enumerate(scenes):
            src = s["source"]
            # Quantize caption boundaries to frames, then keep each frame unchanged.
            boundaries = {0, s["frames"]}
            for c in src.get("captions", []):
                boundaries.update((round(c["start"] * fps), round(c["end"] * fps)))
                srt.append(f"{len(srt)+1}\n{subtitle_time(clock+round(c['start']*fps)/fps)} --> {subtitle_time(clock+round(c['end']*fps)/fps)}\n{c['text']}\n")
                cards.append((frame_clock + round(c["start"] * fps), frame_clock + round(c["end"] * fps), c["text"]))
            effects += [(frame_clock / fps + cue["at"], cue["effect"]) for cue in s["sounds"]]
            bounds = sorted(boundaries)
            entries = ["ffconcat version 1.0"]
            last = None
            for j, (a, b) in enumerate(zip(bounds, bounds[1:])):
                if a == b:
                    continue
                text = next((c["text"] for c in src.get("captions", []) if round(c["start"]*fps) <= a < round(c["end"]*fps)), "")
                name = f"plate-{i}-{j}.png"
                plate(work / name, s, text if caption_style == "band" else "", width, height, font, plan.get('captionSize'), header, background, plan["_colours"], caption_style)
                entries += [f"file '{name}'", f"option framerate {fps}", f"duration {(b-a)/fps:.9f}"]
                last = name
            entries += [f"file '{last}'", f"option framerate {fps}"]
            listing = work / f"plates-{i}.ffconcat"
            listing.write_text("\n".join(entries) + "\n", encoding="utf-8")
            inputs += ["-f", "concat", "-safe", "0", "-i", listing]
            plate_index = input_index
            input_index += 1
            if src["kind"] == "clip":
                inputs += ["-ss", str(s["clipStart"]), "-t", str(s["clipEnd"]-s["clipStart"]), "-i", s["visual"]]
                crop = src.get('crop')
                cropfilter = f'crop={crop[2]-crop[0]}:{crop[3]-crop[1]}:{crop[0]}:{crop[1]},' if crop else ''
                camera = ""
                if s["camera"]:
                    # An editorial camera move, made on the source pixels before they are fitted, so a sharp capture
                    # keeps its detail when the camera pushes in. One frame out per frame in: speed and timing hold.
                    camera = frame_view(*camera_expressions(s["camera"], fps)) + ","
                filters.append(f"[{input_index}:v]setpts=PTS-STARTPTS,{cropfilter}fps={fps},{camera}scale={width}:{body}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{body}:(ow-iw)/2:(oh-ih)/2:color={fill},pad={width}:{height}:0:{hhead}:color={fill},tpad=stop_mode=clone:stop_duration={s['seconds']},trim=end_frame={s['frames']}[base{i}]")
                filters.append(f"[base{i}][{plate_index}:v]overlay=0:0:eof_action=repeat[composite{i}]")
                vf = f"[composite{i}]"
                input_index += 1
            elif s["motion"] == "push":
                from PIL import Image, ImageOps
                still = work / f"still-{i}.png"
                with Image.open(s["visual"]) as raw:
                    shot = ImageOps.exif_transpose(raw).convert("RGB")
                    (shot.crop(src["crop"]) if src.get("crop") else shot).save(still)
                inputs += ["-loop", "1", "-framerate", fps, "-t", f"{s['frames']/fps:.6f}", "-i", still]
                # An editorial camera move, drawn to a fraction of a pixel so the slow push glides instead of shimmering.
                z = f"1+{PUSH}*on/{s['frames']}"
                push = frame_view(z, f"W/2-W/({z})/2", f"H/2-H/({z})/2")
                filters.append(f"[{input_index}:v]scale={width}:{body}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{body}:(ow-iw)/2:(oh-ih)/2:color={fill},{push},pad={width}:{height}:0:{hhead}:color={fill},trim=end_frame={s['frames']}[base{i}]")
                filters.append(f"[base{i}][{plate_index}:v]overlay=0:0:eof_action=repeat[composite{i}]")
                vf = f"[composite{i}]"
                input_index += 1
            else:
                vf = f"[{plate_index}:v]"
            filters.append(f"{vf}fps={fps},trim=end_frame={s['frames']},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]")
            if s["audio"]:
                inputs += ["-i", s["audio"]]
            else:
                inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            filters.append(f"[{input_index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=end_sample={s['frames']*48000//fps},asetpts=PTS-STARTPTS[a{i}]")
            input_index += 1
            concat.append(f"[v{i}][a{i}]")
            receipt.append({"scene": i+1, "title": src["title"], "kind": src["kind"], "status": src["status"], "start": clock, "end": clock+s["seconds"], "crop":src.get('crop'), "motion": s["motion"], "camera": s["camera"], "sounds": s["sounds"], "visualSha256": digest(s["visual"]), "audioSha256": digest(s["audio"]) if s["audio"] else None, "evidence": src.get("evidence", {}), "captureIdentityVerified": False})
            clock += s["seconds"]
            frame_clock += s["frames"]
        transition = plan.get("transition") if len(scenes) > 1 else None
        if transition:
            # Each scene but the last is extended by the fade with its final frame, so the next scene starts
            # on its planned frame and fades in over that hold. Scene times, captions and the SRT do not move.
            # Only the picture fades: the header and caption bands come from a hard-cut copy, so a scene's caption
            # and title appear at full strength on its first frame, exactly when its SRT cue starts.
            fade = round(transition["seconds"] * fps)
            bands = ([(0, hhead)] if hhead else []) + ([(height - hfoot, hfoot)] if hfoot else [])
            for i in range(len(scenes)):
                filters.append(f"[v{i}]split[f{i}][h{i}]" if bands else f"[v{i}]null[f{i}]")
            for i in range(len(scenes) - 1):
                filters.append(f"[f{i}]tpad=stop={fade}:stop_mode=clone[e{i}]")
            previous, offset = "e0", scenes[0]["frames"]
            for i in range(1, len(scenes)):
                out = "faded" if i == len(scenes) - 1 else f"x{i}"
                nxt = f"e{i}" if i < len(scenes) - 1 else f"f{i}"
                filters.append(f"[{previous}][{nxt}]xfade=transition=fade:duration={fade/fps:.6f}:offset={offset/fps:.6f}[{out}]")
                previous, offset = out, offset + scenes[i]["frames"]
            if bands:
                filters.append("".join(f"[h{i}]" for i in range(len(scenes))) + f"concat=n={len(scenes)}:v=1:a=0[hard]")
                filters.append(f"[hard]split={len(bands)}" + "".join(f"[hb{k}]" for k in range(len(bands))))
                current = "faded"
                for k, (y, h) in enumerate(bands):
                    out = "v" if k == len(bands) - 1 else f"banded{k}"
                    filters.append(f"[hb{k}]crop={width}:{h}:0:{y}[band{k}]")
                    filters.append(f"[{current}][band{k}]overlay=0:{y}[{out}]")
                    current = out
            else:
                filters.append("[faded]null[v]")
            filters.append("".join(f"[a{i}]" for i in range(len(scenes))) + f"concat=n={len(scenes)}:v=0:a=1[voice]")
        else:
            filters.append("".join(concat) + f"concat=n={len(scenes)}:v=1:a=1[v][voice]")
        video, audio = "v", "voiced"
        if caption_style == "lowerThird":
            # One overlay track for the whole film, cut on the same frames as the SRT, laid over the finished
            # picture after any crossfade, so each caption is at full strength from its first frame.
            listing, position, n = ["ffconcat version 1.0"], 0, 0
            for a, b, text in cards + [(total, total, "")]:
                for start, end, value in ((position, a, ""), (a, b, text)):
                    if end > start:
                        name = f"lower-third-{n}.png"
                        n += 1
                        lower_third(work / name, value, width, height, font, plan.get("captionSize"), plan["_lowerThird"])
                        listing += [f"file '{name}'", f"option framerate {fps}", f"duration {(end-start)/fps:.9f}"]
                        last = name
                position = max(position, b)
            listing += [f"file '{last}'", f"option framerate {fps}"]
            (work / "lower-thirds.ffconcat").write_text("\n".join(listing) + "\n", encoding="utf-8")
            inputs += ["-f", "concat", "-safe", "0", "-i", work / "lower-thirds.ffconcat"]
            filters.append(f"[{input_index}:v]fps={fps},trim=end_frame={total},setpts=PTS-STARTPTS,format=rgba[cards]")
            filters.append(f"[v][cards]overlay=0:0:eof_action=repeat,format=yuv420p[captioned]")
            video, input_index = "captioned", input_index + 1
        voiced = any(s["audio"] for s in scenes)
        # An accepted music option, even {}, plays at its level (0.3 unless given).
        music = {"level": plan["music"].get("level", .3)} if plan.get("music") is not None else None
        filters.append(("[voice]loudnorm=I=-18:TP=-2:LRA=11,aresample=48000" if voiced else "[voice]anull") + (",asplit=2[voiced][key]" if music and voiced else "[voiced]"))
        mix = ["[voiced]"]
        if music:
            # A generated bed under the voice, pressed down further (sidechain) while the narrator speaks.
            command([sys.executable, "-I", SOUNDBED, f"{bed_length(total / fps):.3f}", work / "bed.wav"])
            inputs += ["-i", work / "bed.wav"]
            filters.append(f"[{input_index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={music['level']}[bed]")
            if voiced:
                filters.append("[bed][key]sidechaincompress=threshold=0.025:ratio=7:attack=25:release=450[ducked]")
            mix.append("[ducked]" if voiced else "[bed]")
            input_index += 1
        for effect in sorted({effect for _, effect in effects}):
            # Generated, like the bed: no third-party sound ships with the skill.
            command([sys.executable, "-I", SFX, effect, work / f"{effect}.wav"])
        for n, (at, effect) in enumerate(effects):
            inputs += ["-i", work / f"{effect}.wav"]
            filters.append(f"[{input_index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={EFFECTS[effect]},adelay={round(at * 1000)}:all=1[fx{n}]")
            mix.append(f"[fx{n}]")
            input_index += 1
        if len(mix) > 1:
            # The voice is first and already the film's exact length; the limiter keeps a click over a loud word from clipping.
            filters.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.94:latency=1[mixed]")
            audio = "mixed"
        # The film opens from and closes to the frame colour, picture and sound together. Frame counts do not change.
        film_fade = plan.get("fade") or {}
        fade_in, fade_out = round(film_fade.get("in", 0) * fps), round(film_fade.get("out", 0) * fps)
        picture_fades = ([f"fade=t=in:s=0:n={fade_in}:c={fill}"] if fade_in else []) + ([f"fade=t=out:s={total - fade_out}:n={fade_out}:c={fill}"] if fade_out else [])
        sound_fades = ([f"afade=t=in:d={fade_in / fps:.6f}"] if fade_in else []) + ([f"afade=t=out:st={(total - fade_out) / fps:.6f}:d={fade_out / fps:.6f}"] if fade_out else [])
        if picture_fades:
            filters.append(f"[{video}]{','.join(picture_fades)}[opened]")
            video = "opened"
        filters.append(f"[{video}]scale=in_range=auto:out_range=tv:out_color_matrix=bt709,format=yuv420p,setrange=limited[encoded]")
        video = "encoded"
        filters.append(f"[{audio}]{','.join(sound_fades) or 'anull'}[a]")
        graph = work / "graph.txt"
        graph.write_text(";\n".join(filters), encoding="utf-8")
        final = work / ("silent-preview.mp4" if silent_preview else "walkthrough.mp4")
        command(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex_threads", "1", graph_option(), graph, "-map", f"[{video}]", "-map", "[a]", "-map_metadata", "-1", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", fps, "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-movflags", "+faststart", final])
        command(["ffmpeg", "-v", "error", "-i", final, "-f", "null", "-"])
        actual = probe(final)
        vs = next(x for x in actual["streams"] if x["codec_type"] == "video")
        if int(vs.get("nb_frames", -1)) != total:
            raise ValueError("Encoded frame count differs from the plan")
        package = work / "result"
        package.mkdir()
        shutil.move(final, package / final.name)
        (package / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
        (package / "narration.txt").write_text("\n\n".join(f"{i+1}. {s['source']['title']}\n{s['source'].get('say', '')}" for i, s in enumerate(scenes)) + "\n", encoding="utf-8")
        # No local filesystem paths or audio credentials are written to the receipt.
        (package / "evidence.json").write_text(json.dumps({"version": 1, "preview": silent_preview, "voice":plan.get('voice'), "videoSha256":digest(package/final.name), "planSha256": digest(plan_path), "fontSha256": digest(font) if font else None, "fps": fps, "frames": sum(s["frames"] for s in scenes), "presentation": {"header": header, "background": background, "transition": transition, "captionStyle": caption_style, "music": music, "fade": plan.get("fade"), "soundEffects": "generated by scripts/sfx.py" if effects else None}, "scenes": receipt, "checks": {"decode": "passed", "frameCount": "passed", "visualReview": "pending", "narrationReview": "pending", "fullPlayback": "pending"}}, indent=2), encoding="utf-8")
        shutil.move(package, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check", action="store_true", help="Validate assets and timing without encoding")
    parser.add_argument("--silent-preview", action="store_true", help="Allow absent narration (music and sound effects still play); mark output as preview")
    args = parser.parse_args()
    try:
        if args.check:
            _, scenes, _ = prepare(args.plan, args.silent_preview)
            print(f"Plan valid: {len(scenes)} scenes, {sum(s['seconds'] for s in scenes):.2f}s; semantic QA pending")
        else:
            if not args.output:
                parser.error("output directory required unless --check")
            out = render(args.plan, args.output, args.silent_preview)
            receipt = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
            preview = receipt.get("preview")
            kind = "silent preview (not a finished video)" if preview else "video"
            video = out / ("silent-preview.mp4" if preview else "walkthrough.mp4")
            print(f"Rendered {kind}: {len(receipt['scenes'])} scenes, {receipt['frames'] / receipt['fps']:.2f}s -> {video}"
                  f" (+ captions.srt, evidence.json). Pending: run qa.py, then the user's full playback with sound")
    except (ValueError, OSError, KeyError, TypeError) as e:
        parser.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
