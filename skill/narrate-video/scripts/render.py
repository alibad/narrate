#!/usr/bin/env python3
"""Offline, frame-counted walkthrough assembly. No network or capture driver."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def command(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"{Path(str(args[0])).name} failed: {result.stderr[-1800:]}")
    return result.stdout


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def audio_peak(path):
    check = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "-"], capture_output=True, text=True)
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
    plan = json.loads(plan_path.read_text())
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
        if not font and any(ord(c) > 255 for c in title + "".join(c["text"] for c in captions)):
            raise ValueError("Supply a suitably licensed font for this script; inspect shaping in the result")
        if any('\u0600' <= c <= '\u06ff' for c in title + ''.join(c['text'] for c in captions)):
            from PIL import features
            if not features.check('raqm'):
                raise ValueError('Arabic captions require Pillow RAQM shaping support')
        prepared.append(dict(source={**s, "title": title}, visual=visual, audio=audio, seconds=duration, frames=frames, clipStart=start, clipEnd=end))
    return plan, prepared, font


def subtitle_time(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


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


def plate(path, scene, text, width, height, font_path, caption_size=None):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    hhead, hfoot = 2*round(height * .1/2), 2*round(height * .16/2)
    canvas = Image.new("RGBA", (width, height), (16, 24, 32, 255))
    if scene["source"]["kind"] == "still":
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
    titlesize = max(12, round(min(size*.85, hhead*.32)))
    titlefont = ImageFont.truetype(str(font_path), titlesize) if font_path else ImageFont.load_default(size=titlesize)
    title = scene["source"]["title"]
    status = scene["source"]["status"].upper()
    margin = round(width * .025)
    label = title
    if draw.textlength(label, font=titlefont) > width - 2 * margin:
        raise ValueError("Header overflows; shorten the scene title")
    draw.text((margin, max(6, hhead*.15)), status, font=titlefont, fill='#85d4c5')
    draw.text((margin, max(6, hhead*.53)), label, font=titlefont, fill="white")
    lines = caption_lines(text, lambda value: draw.textlength(value, font=font), width - 2*margin)
    y = height - hfoot + (hfoot - len(lines) * size * 1.25) / 2
    for line in lines:
        rtl = any('\u0600' <= c <= '\u06ff' for c in line)
        draw.text(((width - draw.textlength(line, font=font)) / 2, y), line, font=font, fill="white", **({'direction':'rtl','language':'ar'} if rtl else {}))
        y += size * 1.25
    canvas.save(path)


def render(plan_path, destination, silent_preview=False):
    plan, scenes, font = prepare(plan_path, silent_preview)
    if destination.exists():
        raise ValueError("Output directory already exists; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = plan.get("width", 1920), plan.get("height", 1080), plan.get("fps", 30)
    with tempfile.TemporaryDirectory(prefix="narrate-video-", dir=destination.parent) as workdir:
        work = Path(workdir)
        inputs, filters, concat, srt, receipt = [], [], [], [], []
        clock, input_index = 0, 0
        for i, s in enumerate(scenes):
            src = s["source"]
            # Quantize caption boundaries to frames, then keep each frame unchanged.
            boundaries = {0, s["frames"]}
            for c in src.get("captions", []):
                boundaries.update((round(c["start"] * fps), round(c["end"] * fps)))
                srt.append(f"{len(srt)+1}\n{subtitle_time(clock+round(c['start']*fps)/fps)} --> {subtitle_time(clock+round(c['end']*fps)/fps)}\n{c['text']}\n")
            bounds = sorted(boundaries)
            entries = ["ffconcat version 1.0"]
            last = None
            for j, (a, b) in enumerate(zip(bounds, bounds[1:])):
                if a == b:
                    continue
                text = next((c["text"] for c in src.get("captions", []) if round(c["start"]*fps) <= a < round(c["end"]*fps)), "")
                name = f"plate-{i}-{j}.png"
                plate(work / name, s, text, width, height, font, plan.get('captionSize'))
                entries += [f"file '{name}'", f"option framerate {fps}", f"duration {(b-a)/fps:.9f}"]
                last = name
            entries += [f"file '{last}'", f"option framerate {fps}"]
            listing = work / f"plates-{i}.ffconcat"
            listing.write_text("\n".join(entries) + "\n")
            inputs += ["-f", "concat", "-safe", "0", "-i", listing]
            plate_index = input_index
            input_index += 1
            if src["kind"] == "clip":
                inputs += ["-ss", str(s["clipStart"]), "-t", str(s["clipEnd"]-s["clipStart"]), "-i", s["visual"]]
                hhead, hfoot = 2*round(height*.1/2), 2*round(height*.16/2)
                body = height - hhead - hfoot
                crop = src.get('crop')
                cropfilter = f'crop={crop[2]-crop[0]}:{crop[3]-crop[1]}:{crop[0]}:{crop[1]},' if crop else ''
                filters.append(f"[{input_index}:v]setpts=PTS-STARTPTS,{cropfilter}fps={fps},scale={width}:{body}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{body}:(ow-iw)/2:(oh-ih)/2:color=0x101820,pad={width}:{height}:0:{hhead}:color=0x101820,tpad=stop_mode=clone:stop_duration={s['seconds']},trim=end_frame={s['frames']}[base{i}]")
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
            receipt.append({"scene": i+1, "title": src["title"], "kind": src["kind"], "status": src["status"], "start": clock, "end": clock+s["seconds"], "crop":src.get('crop'), "visualSha256": digest(s["visual"]), "audioSha256": digest(s["audio"]) if s["audio"] else None, "evidence": src.get("evidence", {}), "captureIdentityVerified": False})
            clock += s["seconds"]
        filters.append("".join(concat) + f"concat=n={len(scenes)}:v=1:a=1[v][voice]")
        filters.append("[voice]loudnorm=I=-18:TP=-2:LRA=11,aresample=48000[a]" if any(s["audio"] for s in scenes) else "[voice]anull[a]")
        graph = work / "graph.txt"
        graph.write_text(";\n".join(filters))
        final = work / ("silent-preview.mp4" if silent_preview else "walkthrough.mp4")
        command(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex_threads", "1", "-filter_complex", graph.read_text(), "-map", "[v]", "-map", "[a]", "-map_metadata", "-1", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", fps, "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-movflags", "+faststart", final])
        command(["ffmpeg", "-v", "error", "-i", final, "-f", "null", "-"])
        actual = probe(final)
        vs = next(x for x in actual["streams"] if x["codec_type"] == "video")
        if int(vs.get("nb_frames", -1)) != sum(s["frames"] for s in scenes):
            raise ValueError("Encoded frame count differs from the plan")
        package = work / "result"
        package.mkdir()
        shutil.move(final, package / final.name)
        (package / "captions.srt").write_text("\n".join(srt))
        (package / "narration.txt").write_text("\n\n".join(f"{i+1}. {s['source']['title']}\n{s['source'].get('say', '')}" for i, s in enumerate(scenes)) + "\n")
        # No local filesystem paths or audio credentials are written to the receipt.
        (package / "evidence.json").write_text(json.dumps({"version": 1, "preview": silent_preview, "voice":plan.get('voice'), "videoSha256":digest(package/final.name), "planSha256": digest(plan_path), "fontSha256": digest(font) if font else None, "fps": fps, "frames": sum(s["frames"] for s in scenes), "scenes": receipt, "checks": {"decode": "passed", "frameCount": "passed", "visualReview": "pending", "narrationReview": "pending", "fullPlayback": "pending"}}, indent=2))
        shutil.move(package, destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--check", action="store_true", help="Validate assets and timing without encoding")
    parser.add_argument("--silent-preview", action="store_true", help="Allow absent narration; mark output as preview")
    args = parser.parse_args()
    try:
        if args.check:
            _, scenes, _ = prepare(args.plan, args.silent_preview)
            print(f"Plan valid: {len(scenes)} scenes, {sum(s['seconds'] for s in scenes):.2f}s; semantic QA pending")
        else:
            if not args.output:
                parser.error("output directory required unless --check")
            print(render(args.plan, args.output, args.silent_preview))
    except (ValueError, OSError, KeyError, TypeError) as e:
        parser.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
