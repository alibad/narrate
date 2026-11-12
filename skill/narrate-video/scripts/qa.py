#!/usr/bin/env python3
"""Decode, measure loudness, extract cut frames and compare ordered transcripts. Human review stays pending."""
import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path
from render import command, probe, digest


# Arabic harakat (short vowels, shadda, sukun, U+064B–U+065F and U+0670) and tatweel (U+0640) are dropped from both
# sides on purpose: transcripts rarely carry them, so a diacritized script still matches. Every other combining mark
# stays inside its word, so Hindi कि and की, or Thai กิน and กัน, stay different words.
ARABIC_DIACRITICS = re.compile('[\u0640\u064b-\u065f\u0670]')


def wordlike(c):
    return unicodedata.category(c)[0] in 'LNM'


def words(text):
    """Ordered words: runs of letters, digits and combining marks. An apostrophe between letters stays in the word,
    and a sign directly before a number stays on it (-50 is not 50). Order, repetition and negations are kept."""
    text = ARABIC_DIACRITICS.sub('', unicodedata.normalize('NFC', text)).casefold()
    out, cur = [], ''
    for i, c in enumerate(text):
        after = text[i+1] if i+1 < len(text) else ''
        if wordlike(c):
            cur += c
        elif c in "'’" and cur and after and wordlike(after):
            cur += c
        elif c in '+-−' and not cur and after.isdigit() and not (i and wordlike(text[i-1])):
            cur = '+' if c == '+' else '-'
        else:
            if cur: out.append(cur)
            cur = ''
    if cur: out.append(cur)
    return out


ONES='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS='_ _ twenty thirty forty fifty sixty seventy eighty ninety'.split()


def spoken(n):
    if n<20:return ONES[n]
    if n<100:return TENS[n//10]+('' if n%10==0 else ' '+ONES[n%10])
    for size,name in ((10**9,'billion'),(10**6,'million'),(1000,'thousand'),(100,'hundred')):
        if n>=size:
            head,rest=divmod(n,size)
            return spoken(head)+' '+name+('' if not rest else ' '+spoken(rest))


def english_numbers(text):
    # ASR writes "2,000", "71%" and "-50" where the script says "two thousand", "seventy-one percent" and
    # "minus fifty". A sign counts only at the start of a token, so "3-5" and "COVID-19" are not negatives.
    def say(m):
        out=spoken(int(m.group(2).replace(',','')))
        if m.group(3):out+=' point '+' '.join(ONES[int(d)] for d in m.group(3))
        sign={'-':'minus ','−':'minus ','+':'plus '}.get(m.group(1) or '','')
        return f" {sign}{out}{' percent' if m.group(4) else ''} "
    return re.sub(r'(?:(?<![\w.])([-−+])(?=\d))?(?<!\w)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%)?',say,text)


def compare(expected, heard, language=''):
    numbers=language.casefold().startswith('en')
    if numbers:expected,heard=english_numbers(expected),english_numbers(heard)
    a,b=words(expected),words(heard)
    changes=[dict(op=op,expected=a[i:j],heard=b[k:l]) for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes() if op!='equal']
    return dict(exactOrderedMatch=bool(a) and a==b,changes=changes,expectedWords=len(a),heardWords=len(b),numbersAsWords=numbers)


def spoken_script(narration, titles):
    """Drop the renderer's scene headings (`N. Title` opening each block); keep every spoken line, numbered or not."""
    lines=narration.splitlines();out=[];n=0
    for i,line in enumerate(lines):
        if n<len(titles) and line==f'{n+1}. {titles[n]}' and (i==0 or not lines[i-1].strip()):n+=1;continue
        out.append(line)
    return '\n'.join(out)


def inspect(video, evidence, output, transcript=None):
    if output.exists(): raise ValueError('QA output exists')
    data=json.loads(evidence.read_text(encoding='utf-8')); info=probe(video)
    if data.get('videoSha256')!=digest(video): raise ValueError('Evidence does not match this export')
    output.mkdir(parents=True)
    command(['ffmpeg','-v','error','-i',video,'-f','null','-'])
    vs=next(s for s in info['streams'] if s['codec_type']=='video')
    times={0,max(0,float(vs['duration'])-1/int(data['fps']))}
    for s in data['scenes']:
        times.update([s['start'],(s['start']+s['end'])/2,max(s['start'],s['end']-1/data['fps'])])
    from PIL import Image,ImageDraw,ImageOps
    thumbs=[]
    # Cells follow the film's shape so a landscape export is not shrunk into portrait cells.
    landscape=int(vs['width'])>int(vs['height'])
    (w,h),cols=((640,360),3) if landscape else ((390,680),4)
    for i,t in enumerate(sorted(times)):
        path=output/f'frame-{i:03d}.png'
        command(['ffmpeg','-v','error','-ss',t,'-i',video,'-frames:v','1',path])
        im=Image.open(path).convert('RGB');thumb=Image.new('RGB',(w,h+40),'#17262f')
        small=ImageOps.contain(im,(w,h));thumb.paste(small,((w-small.width)//2,22))
        ImageDraw.Draw(thumb).text((10,5),f'{t:.3f} s',fill='white');thumbs.append(thumb)
    sheet=Image.new('RGB',(w*min(cols,len(thumbs)),(h+40)*-(-len(thumbs)//cols)),'#17262f')
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%cols)*w,(i//cols)*(h+40)))
    sheet.save(output/'contact-sheet.jpg')
    import subprocess
    p=subprocess.run(['ffmpeg','-hide_banner','-i',str(video),'-af','loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace')
    match=re.search(r'\{\s*"input_i".*?\}',p.stderr,re.S)
    if p.returncode or not match: raise ValueError('Loudness measurement failed')
    loudness=json.loads(match.group())
    report=dict(videoSha256=digest(video),decode='passed',probe=info,loudness=loudness,
                audioTranscript='pending',visualReview='pending',captionAlignment='pending',fullPlayback='pending')
    if transcript:
        text=(video.parent/'narration.txt').read_text(encoding='utf-8')
        text=spoken_script(text,[s.get('title','') for s in data.get('scenes',[])])
        report['audioTranscript']=compare(text,transcript.read_text(encoding='utf-8'),(data.get('voice') or {}).get('language',''))
        report['transcriptSha256']=digest(transcript)
    (output/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path);p.add_argument('evidence',type=Path);p.add_argument('output',type=Path);p.add_argument('--transcript',type=Path)
    a=p.parse_args();r=inspect(a.video,a.evidence,a.output,a.transcript);t=r['audioTranscript'];l=r['loudness']
    heard='not compared (pass --transcript)' if t=='pending' else 'exact ordered match' if t['exactOrderedMatch'] else f"{len(t['changes'])} difference(s) to review"
    print(f"Decode passed; {l['input_i']} LUFS, {l['input_tp']} dBTP; transcript: {heard}. Pending: visual review, caption timing, full playback. Details: {a.output/'qa.json'}")
