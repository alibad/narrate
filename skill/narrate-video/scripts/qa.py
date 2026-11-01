#!/usr/bin/env python3
"""Decode, measure loudness, extract cut frames and compare ordered transcripts. Human review stays pending."""
import argparse
import difflib
import json
import re
from pathlib import Path
from render import command, probe, digest


def words(text):
    # Preserve numbers, negations, Arabic letter distinctions, order and repetition.
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text.casefold(), re.UNICODE)


def compare(expected, heard):
    a,b=words(expected),words(heard)
    changes=[dict(op=op,expected=a[i:j],heard=b[k:l]) for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes() if op!='equal']
    return dict(exactOrderedMatch=bool(a) and a==b,changes=changes,expectedWords=len(a),heardWords=len(b))


def inspect(video, evidence, output, transcript=None):
    if output.exists(): raise ValueError('QA output exists')
    data=json.loads(evidence.read_text()); info=probe(video)
    if data.get('videoSha256')!=digest(video): raise ValueError('Evidence does not match this export')
    output.mkdir(parents=True)
    command(['ffmpeg','-v','error','-i',video,'-f','null','-'])
    vs=next(s for s in info['streams'] if s['codec_type']=='video')
    times={0,max(0,float(vs['duration'])-1/int(data['fps']))}
    for s in data['scenes']:
        times.update([s['start'],(s['start']+s['end'])/2,max(s['start'],s['end']-1/data['fps'])])
    from PIL import Image,ImageDraw,ImageOps
    thumbs=[]
    for i,t in enumerate(sorted(times)):
        path=output/f'frame-{i:03d}.png'
        command(['ffmpeg','-v','error','-ss',t,'-i',video,'-frames:v','1',path])
        im=Image.open(path).convert('RGB');thumb=Image.new('RGB',(390,720),'#17262f')
        small=ImageOps.contain(im,(390,680));thumb.paste(small,((390-small.width)//2,22))
        ImageDraw.Draw(thumb).text((10,5),f'{t:.3f} s',fill='white');thumbs.append(thumb)
    sheet=Image.new('RGB',(390*min(4,len(thumbs)),720*((len(thumbs)+3)//4)),'#17262f')
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%4)*390,(i//4)*720))
    sheet.save(output/'contact-sheet.jpg')
    import subprocess
    p=subprocess.run(['ffmpeg','-hide_banner','-i',str(video),'-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    match=re.search(r'\{\s*"input_i".*?\}',p.stderr,re.S)
    if p.returncode or not match: raise ValueError('Loudness measurement failed')
    loudness=json.loads(match.group())
    report=dict(videoSha256=digest(video),decode='passed',probe=info,loudness=loudness,
                audioTranscript='pending',visualReview='pending',captionAlignment='pending',fullPlayback='pending')
    if transcript:
        text=(video.parent/'narration.txt').read_text()
        # Renderer headings occupy separate numbered lines; exclude them from expected speech.
        text='\n'.join(line for line in text.splitlines() if not re.match(r'^\d+\. ',line))
        report['audioTranscript']=compare(text,transcript.read_text())
        report['transcriptSha256']=digest(transcript)
    (output/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path);p.add_argument('evidence',type=Path);p.add_argument('output',type=Path);p.add_argument('--transcript',type=Path)
    a=p.parse_args();inspect(a.video,a.evidence,a.output,a.transcript)
