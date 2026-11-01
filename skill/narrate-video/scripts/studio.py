#!/usr/bin/env python3
"""Build a network-free voice audition page from approved audio and explicit identities."""
import argparse
import html
import json
import shutil
from pathlib import Path
from render import asset, probe, digest


def build(spec_path, output):
    root=spec_path.resolve().parent; spec=json.loads(spec_path.read_text(encoding='utf-8'))
    if output.exists(): raise ValueError('Audition output exists')
    takes=spec.get('takes',[])
    if not takes: raise ValueError('Provide approved audition takes')
    cards=[]; files=[]
    for i,t in enumerate(takes):
        for k in ('name','provider','model','revision','language','text'):
            if not isinstance(t.get(k),str) or not t[k].strip(): raise ValueError(f'Missing audition identity: {k}')
        path=asset(root,t['audio']); info=probe(path)
        if not any(s['codec_type']=='audio' for s in info['streams']): raise ValueError('Audition has no audio')
        safe={k:t[k] for k in ('name','provider','model','revision','language','text')}
        safe['audioSha256']=digest(path); files.append((path,f'take-{i}{path.suffix}'))
        identity=html.escape(json.dumps(safe,ensure_ascii=False),quote=True)
        e=lambda k:html.escape(t[k])
        cards.append(f'''<section class="take" data-id="{i}"><div class="top"><h2>{e('name')}</h2><span>{e('language')}</span></div>
<p class="model">{e('model')}</p><p class="detail">{e('provider')} · revision {e('revision')}</p>
<p class="line" dir="auto">{e('text')}</p><audio controls preload="metadata" src="take-{i}{path.suffix}"></audio>
<button class="choose" id="choose-{i}" data-identity="{identity}">Choose {e('name')}</button></section>''')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; media-src 'self' file:; img-src 'self'; connect-src 'none'">
<title>Voice auditions</title><style>
*{box-sizing:border-box}body{margin:0;background:#101820;color:#edf7f5;font:22px/1.4 system-ui,sans-serif;padding:32px}
main{max-width:1080px;margin:auto}header{margin-bottom:24px}.eyebrow{color:#85d4c5;font-size:19px;letter-spacing:.1em;margin:0}
h1{font-size:44px;line-height:1.12;margin:12px 0}.intro{color:#bfcecf;margin:0;font-size:22px}
.takes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.take{border:2px solid #3d565d;border-radius:18px;padding:24px;background:#17262f}
.take.selected{border-color:#85d4c5;background:#183a39}.top{display:flex;justify-content:space-between;align-items:center}h2{font-size:36px;margin:0}.top span{color:#85d4c5;font-size:22px}
.model{font-size:23px;margin:14px 0 6px;overflow-wrap:anywhere}.detail{font-size:18px;color:#bfcecf;margin:0}.line{font-size:24px;min-height:100px}audio{display:block;width:100%;height:46px}
button{display:block;width:100%;border:0;border-radius:10px;background:#85d4c5;color:#102d29;font:600 24px/1.3 system-ui;padding:15px;cursor:pointer;margin-top:18px}
button:focus-visible{outline:4px solid white;outline-offset:3px}button:disabled{opacity:.75;cursor:default}#selection{font-size:26px;padding:20px 0 0;margin:0}footer{color:#bfcecf;font-size:18px;margin-top:18px}#export{max-width:320px;background:#2b444b;color:white;font-size:20px;margin-top:10px}
@media(max-width:700px){body{padding:24px}.takes{grid-template-columns:1fr;gap:14px}.take{padding:16px}.line{min-height:0;font-size:21px;margin:12px 0}.choose{padding:10px;font-size:23px;margin-top:12px}h1{font-size:40px}.intro{font-size:23px}.model{font-size:25px;margin:10px 0 5px}.detail{font-size:20px}h2{font-size:38px}}
</style><main><header><p class="eyebrow">WALKTHROUGH VIDEO / AUDITIONS</p><h1>A voice you can identify</h1><p class="intro">Compare the same sentence. Choose a take.</p></header><div class="takes">CARDS</div>
<p id="selection" role="status">No voice selected</p><button id="export" disabled>Save voice choice</button><footer>Local audition files. Playback and selection stay local.</footer></main>
<script>let choice=null;document.querySelectorAll('.choose').forEach(b=>b.onclick=()=>{
choice=JSON.parse(b.dataset.identity);document.querySelectorAll('.take').forEach(t=>t.classList.remove('selected'));
b.closest('.take').classList.add('selected');document.getElementById('selection').textContent='Selected: '+choice.name+' · '+choice.language;
document.getElementById('export').disabled=false;});
document.getElementById('export').onclick=()=>{if(!choice)return;const u=URL.createObjectURL(new Blob([JSON.stringify(choice,null,2)],{type:'application/json'}));
const a=document.createElement('a');a.href=u;a.download='voice-choice.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};</script></html>'''.replace('CARDS',''.join(cards))
    output.mkdir(parents=True)
    try:
        for source,name in files:shutil.copyfile(source,output/name)
        (output/'index.html').write_text(page,encoding='utf-8')
    except Exception:
        shutil.rmtree(output);raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('spec',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();build(a.spec,a.output)
