"""Assemble real captured states and measured phrase audio with the bundled skill."""
import importlib.util,json,hashlib,subprocess,sys,shutil,datetime,re
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'skill/narrate-video/scripts'
spec=importlib.util.spec_from_file_location('film_renderer',SCRIPTS/'render.py');renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
films=json.loads((ROOT/'content/gallery.json').read_text());sheet=Image.new('RGB',(1200,len(films)*238),'#f7f5ef');draw=ImageDraw.Draw(sheet)
colors=['#d4d9db','#c9c3b3','#d7bf9d','#d7b9a1','#c4cdbf','#c4bfce','#d2c1b5','#c7cbb2','#c9bda8','#c7bdc9']
for row,item in enumerate(films):
 folder=ROOT/'production'/item['id'];scenes=[]
 captures=[folder/'captures'/f'{n:02}.jpg'for n in range(1,4)]
 hashes=[hashlib.sha256(p.read_bytes()).hexdigest()for p in captures]
 if len(set(hashes))!=3:raise ValueError(f"Duplicate state captures for {item['id']}")
 voice=json.loads((folder/'speech/01.identity.json').read_text())
 for n,(say,capture)in enumerate(zip(item['narration'],captures),1):
  receipt=json.loads((folder/'speech'/f'{n:02}.identity.json').read_text());wav=folder/'speech'/f'{n:02}.wav'
  seconds=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(wav)]))
  evidence=dict(capturedAt=datetime.datetime.fromtimestamp(capture.stat().st_mtime,datetime.timezone.utc).isoformat(),surface='Chrome browser viewport; screenshot',target=item['url'],action=['Read the article overview','Use the contents link to inspect the topic section','Use the contents link to inspect references'][n-1],build='unknown; public third-party site')
  scenes.append(dict(kind='still',status='observed',title=f"Narrate · {item['language']} · {n:02}/03",visual=f'captures/{n:02}.jpg',audio=f'speech/{n:02}.wav',say=say,captions=[dict(start=0,end=seconds,text=say)],evidence=evidence))
  with Image.open(capture)as img:thumb=img.copy();thumb.thumbnail((390,209));sheet.paste(thumb,(n*400-395,row*238+23))
  draw.text((n*400-395,row*238+5),item['id']+' / '+str(n),fill='#161b24')
 plan=dict(version=1,width=1920,height=1080,fps=30,font='fonts/captions.ttf',captionSize=48,voice=dict(provider='local-voice-studio',model=voice['model'],revision=voice['revision'],name='authorized recorded voice; private review',language=item['id'],referenceLanguage=voice['from_recording'],cloned=True,fallback=False),scenes=scenes)
 plan_path=folder/'plan.json';plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2));dest=folder/'cut-1'
 if not dest.exists():renderer.render(plan_path,dest)
 media=ROOT/'site/media';media.mkdir(exist_ok=True)
 shutil.copyfile(dest/'walkthrough.mp4',media/f"{item['id']}.mp4")
 srt=(dest/'captions.srt').read_text();(media/f"{item['id']}.vtt").write_text('WEBVTT\n\n'+re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})',r'\1.\2',srt))
 duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(media/f"{item['id']}.mp4")]))
 subprocess.run(['ffmpeg','-v','error','-i',str(media/f"{item['id']}.mp4"),'-frames:v','1','-update','1',str(media/f"{item['id']}.jpg")],check=True)
 item.update(status='review',review='pending',video=f"/media/{item['id']}.mp4",vtt=f"/media/{item['id']}.vtt",poster=f"/media/{item['id']}.jpg",duration=round(duration,2),reference=voice['from_recording'],capturedAt='2026-11-01',color=colors[row],sha256=hashlib.sha256((media/f"{item['id']}.mp4").read_bytes()).hexdigest())
 (ROOT/'content/gallery.json').write_text(json.dumps(films,ensure_ascii=False,indent=2));print(item['id'],round(duration,2),'rendered',flush=True)
 sheet.save(ROOT/'production/capture-contact-sheet.jpg')
print('Ten narrated review cuts assembled with source-linked still captures.',flush=True)
