#!/usr/bin/env python3
"""Optional explicit command speech adapter and audio-derived phrase captions. No fallback/cache."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from render import command, probe, digest, audio_peak, asset


def synthesize(config_path, text_path, destination, language, voice):
    cfg = json.loads(config_path.read_text())
    for field in ('provider', 'model', 'revision', 'network'):
        if not isinstance(cfg.get(field), str) or not cfg[field].strip():
            raise ValueError(f'Explicit speech identity required: {field}')
    if cfg['network'] not in ('none', 'explicit'):
        raise ValueError('network must be none or explicit; no fallback exists')
    if language not in cfg.get('languages', []) or voice not in cfg.get('voices', []):
        raise ValueError('Requested language or voice unsupported; no substitution')
    if cfg.get('reference') or cfg.get('cloning'):
        raise ValueError('This adapter accepts preset voices; use an explicitly reviewed external adapter for authorized cloning')
    argv = cfg.get('command')
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError('Supply command as an argv array, never a shell string')
    if not any('{output}' in a for a in argv) or not any('{input}' in a for a in argv):
        raise ValueError('Command must use {input} and {output}')
    text = text_path.read_text().strip()
    if not 1 <= len(text) < 2500:
        raise ValueError('Keep each speech request under 2500 characters')
    if destination.exists():
        raise ValueError('Speech output exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='voice-', dir=destination.parent) as td:
        work = Path(td)
        source, out = work/'input.txt', work/'voice.wav'
        source.write_text(text)
        fields = dict(input=str(source), output=str(out), voice=voice, language=language)
        args = [a.format_map(fields) for a in argv]
        # A selected command is executable code; inspect its behavior before opting in.
        proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if proc.returncode:
            raise ValueError('Selected speech command failed; see local provider logs; no fallback attempted')
        info = probe(out)
        if not any(s['codec_type'] == 'audio' for s in info['streams']) or audio_peak(out) < -55:
            raise ValueError('Selected speech command produced missing or silent audio')
        command(['ffmpeg', '-v', 'error', '-i', out, '-f', 'null', '-'])
        receipt = {k: cfg[k] for k in ('provider','model','revision','network')}
        receipt.update(voice=voice, language=language, cloned=False, textSha256=digest(source),
                       configSha256=digest(config_path), audioSha256=digest(out), transcriptReview='pending')
        (work/'identity.json').write_text(json.dumps(receipt, indent=2))
        # Hard links fail rather than overwrite; both files validated before promotion.
        os.link(work/'identity.json', destination.with_suffix('.identity.json'))
        try: os.link(out, destination)
        except Exception:
            destination.with_suffix('.identity.json').unlink()
            raise
    return receipt


def compose(spec_path, destination):
    """One approved audio file per caption phrase. Cue edges come from audio, never word ratios."""
    if destination.exists(): raise ValueError('Composition output exists')
    spec = json.loads(spec_path.read_text())
    root = spec_path.resolve().parent
    parts = spec['phrases']
    if not parts: raise ValueError('No phrases')
    for p in parts:
        if not isinstance(p.get('text'), str) or not p['text'].strip(): raise ValueError('Missing phrase text')
        p['_path'] = asset(root, p['audio'])
        if audio_peak(p['_path']) < -55: raise ValueError('Silent phrase')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='phrase-', dir=destination.parent) as td:
        work=Path(td); inputs=[]; filters=[]; cues=[]; cursor=0
        for i,p in enumerate(parts):
            inputs += ['-i', p['_path']]
            seconds=float(probe(p['_path'])['format']['duration'])
            # Normalize all files to 48k samples before deriving the final caption timeline.
            samples=round(seconds*48000); duration=samples/48000
            filters.append(f'[{i}:a]aresample=48000,aformat=channel_layouts=mono,apad,atrim=end_sample={samples},asetpts=PTS-STARTPTS[a{i}]')
            cues.append(dict(start=cursor,end=cursor+duration,text=p['text']))
            cursor += duration
        filters.append(''.join(f'[a{i}]' for i in range(len(parts)))+f'concat=n={len(parts)}:v=0:a=1[out]')
        command(['ffmpeg','-v','error',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-c:a','pcm_s16le',work/'narration.wav'])
        data=dict(say=' '.join(p['text'] for p in parts),captions=cues,
                  alignment='phrase-audio-boundaries; playback review required',audioSha256=digest(work/'narration.wav'))
        (work/'captions.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
        # A directory move publishes both artifacts together, without replacing an existing output.
        destination.mkdir()
        try:
            os.link(work/'narration.wav',destination/'narration.wav')
            os.link(work/'captions.json',destination/'captions.json')
        except Exception:
            import shutil
            shutil.rmtree(destination)
            raise
    return data


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__); sub=ap.add_subparsers(dest='mode',required=True)
    s=sub.add_parser('synthesize');s.add_argument('config',type=Path);s.add_argument('text',type=Path);s.add_argument('output',type=Path)
    s.add_argument('--language',required=True);s.add_argument('--voice',required=True)
    c=sub.add_parser('compose');c.add_argument('spec',type=Path);c.add_argument('output',type=Path)
    args=ap.parse_args()
    if args.mode=='synthesize': print(json.dumps(synthesize(args.config,args.text,args.output,args.language,args.voice),indent=2))
    else: print(json.dumps(compose(args.spec,args.output),ensure_ascii=False,indent=2))
