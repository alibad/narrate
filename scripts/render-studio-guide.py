"""Render an explicit studio-film plan and install its local website preview."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skill/narrate-video/scripts'
spec = importlib.util.spec_from_file_location('studio_renderer', SCRIPTS / 'render.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--cut', type=Path, required=True)
    parser.add_argument('--reuse-cut', action='store_true')
    parser.add_argument('--poster', type=Path)
    args = parser.parse_args()
    plan = args.plan.resolve()
    cut = args.cut.resolve()
    if not args.reuse_cut:
        renderer.render(plan, cut)
    receipt = json.loads((cut / 'evidence.json').read_text())
    video = cut / 'walkthrough.mp4'
    if receipt.get('preview'):
        raise ValueError('A silent preview cannot replace the narrated website film')
    if receipt['planSha256'] != renderer.digest(plan):
        raise ValueError('The cut does not match the supplied plan')
    if receipt['videoSha256'] != renderer.digest(video):
        raise ValueError('The cut does not match its video receipt')
    media = ROOT / 'site/media'
    backup = plan.parent / 'previous-site'
    backup.mkdir(exist_ok=True)
    for source in [media / 'studio.mp4', media / 'studio.jpg', media / 'studio.vtt', ROOT / 'site/studio-guide.json']:
        target = backup / source.name
        if source.exists() and not target.exists():
            shutil.copyfile(source, target)
    shutil.copyfile(video, media / 'studio.mp4')
    srt = (cut / 'captions.srt').read_text()
    (media / 'studio.vtt').write_text('WEBVTT\n\n' + re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', srt))
    if args.poster:
        from PIL import Image
        with Image.open(args.poster) as image:
            image.convert('RGB').save(media / 'studio.jpg', quality=95)
    else:
        renderer.command(['ffmpeg', '-v', 'error', '-ss', '1', '-i', video, '-frames:v', '1', '-update', '1', '-y', media / 'studio.jpg'])
    metadata = dict(video='/media/studio.mp4', poster='/media/studio.jpg', vtt='/media/studio.vtt', duration=receipt['frames']/receipt['fps'], language=receipt.get('voice', {}).get('language', 'en'), review='local review cut; full listening review pending', sha256=hashlib.sha256(video.read_bytes()).hexdigest())
    (ROOT / 'site/studio-guide.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f"Installed local studio film: {metadata['duration']:.2f}s. No upload or deployment performed.")


if __name__ == '__main__':
    main()
