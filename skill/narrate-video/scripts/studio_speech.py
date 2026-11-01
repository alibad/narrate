#!/usr/bin/env python3
"""Narrate with the user's accepted local voice profile, without voice fallback."""
import argparse,json,os,tempfile,urllib.parse,urllib.request
from pathlib import Path
from render import command,digest,audio_peak

def generate(text_path,output,language='en',endpoint='http://127.0.0.1:8765'):
    url=urllib.parse.urlparse(endpoint)
    if url.scheme!='http' or url.hostname not in ('localhost','127.0.0.1') or url.username or url.password:
        raise ValueError('Use the selected local studio; this client has no cloud endpoint')
    if output.exists():raise ValueError('Narration output exists')
    text=text_path.read_text().strip()
    if not 1<=len(text)<=2400:raise ValueError('Keep each narration request within 2400 characters')
    with urllib.request.urlopen(endpoint+'/api/status',timeout=10)as r:status=json.load(r)
    c=status['config'];engine=c.get('engine');models=status.get('engines',{})
    if engine not in models or c.get('voice')!='mine' or not c.get('profileReady'):
        raise ValueError('Complete language/model setup and accept your voice auditions in the studio first')
    if language not in c.get('languages',[]) or language not in models[engine]['langs']:
        raise ValueError('Add this language to your voice profile first; no language substitution')
    reference=c.get('references',{}).get(language) or language
    saved=status.get('mine',{}).get(reference);accepted=c.get('accepted',{}).get(language,{})
    if not saved or accepted.get('engine')!=engine or accepted.get('referenceSha256')!=saved['sha256']:
        raise ValueError('The model or reference changed. Accept a fresh audition first')
    output.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(endpoint+'/v1/audio/speech',data=json.dumps({'input':text,'language':language,'engine':engine,'mine':True}).encode(),headers={'Content-Type':'application/json'})
    with tempfile.TemporaryDirectory(prefix='local-voice-',dir=output.parent)as td:
        work=Path(td)
        with urllib.request.urlopen(req,timeout=600)as response:
            if response.headers.get('X-Voice')!=f'{engine}; cloned=True; lang={language}':
                raise ValueError('Studio did not confirm the selected model, language and recorded voice')
            reference_hash=response.headers.get('X-Voice-Reference-SHA256')
            if reference_hash!=saved['sha256']:
                raise ValueError('The reference changed during generation. Review it in the studio first')
            (work/'speech.mp3').write_bytes(response.read())
        command(['ffmpeg','-v','error','-i',work/'speech.mp3','-ar','48000','-ac','1',work/'speech.wav'])
        if audio_peak(work/'speech.wav') < -55:raise ValueError('Local voice output is silent')
        model_info=next(m for m in status['plan']['models'] if m['id']==engine)
        receipt=dict(provider='local-voice-studio',engine=engine,model=model_info['repo'],revision=model_info['revision'],voice='saved-user-recording',referenceLanguage=reference,referenceSha256=reference_hash,language=language,cloned=True,fallback=False,audioSha256=digest(work/'speech.wav'),textSha256=digest(text_path),review='pending')
        (work/'identity.json').write_text(json.dumps(receipt,indent=2))
        os.link(work/'identity.json',output.with_suffix('.identity.json'))
        try:os.link(work/'speech.wav',output)
        except Exception:
            output.with_suffix('.identity.json').unlink();raise
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('text',type=Path);p.add_argument('output',type=Path);p.add_argument('--language',default='en');p.add_argument('--endpoint',default='http://127.0.0.1:8765')
    a=p.parse_args();print(json.dumps(generate(a.text,a.output,a.language,a.endpoint),indent=2))
