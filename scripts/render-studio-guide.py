"""Build the skill's own helper film from observed studio states and local speech."""
from pathlib import Path
import importlib.util,json,datetime,subprocess,shutil,hashlib,re
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'production/studio-guide';SCRIPTS=ROOT/'skill/narrate-video/scripts'
spec=importlib.util.spec_from_file_location('studio_renderer',SCRIPTS/'render.py');renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
phrases=json.loads((FOLDER/'script.json').read_text(encoding='utf-8'));titles=['Choose narration languages','Review compatible models','Set up the selected model','Record or reuse your voice','Listen to each language']
voice=json.loads((FOLDER/'speech/01.identity.json').read_text(encoding='utf-8'));scenes=[]
for i,(text,title)in enumerate(zip(phrases,titles),1):
 audio=FOLDER/'speech'/f'{i:02}.wav';visual=FOLDER/'captures'/f'{i:02}.jpg';secs=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(audio)]))
 scenes.append(dict(kind='still',status='observed',title=f'Narrate · {title}',visual=f'captures/{i:02}.jpg',audio=f'speech/{i:02}.wav',say=text,captions=[dict(start=0,end=secs,text=text)],evidence=dict(capturedAt=datetime.datetime.fromtimestamp(visual.stat().st_mtime,datetime.timezone.utc).isoformat(),surface='Chrome browser viewport; screenshot',target='local Narrate studio',action=title,build='unknown; observed local working build')))
plan=dict(version=1,width=1920,height=1080,fps=30,font='fonts/captions.ttf',captionSize=48,voice=dict(provider='local-voice-studio',model=voice['model'],revision=voice['revision'],name='creator recorded voice',language='en',referenceLanguage='en',cloned=True,fallback=False),scenes=scenes)
(FOLDER/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8');dest=FOLDER/'cut-1';renderer.render(FOLDER/'plan.json',dest)
media=ROOT/'site/media';shutil.copyfile(dest/'walkthrough.mp4',media/'studio.mp4');srt=(dest/'captions.srt').read_text(encoding='utf-8');(media/'studio.vtt').write_text('WEBVTT\n\n'+re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})',r'\1.\2',srt),encoding='utf-8');subprocess.run(['ffmpeg','-v','error','-i',str(media/'studio.mp4'),'-frames:v','1','-update','1',str(media/'studio.jpg')],check=True)
duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(media/'studio.mp4')]))
(ROOT/'site/studio-guide.json').write_text(json.dumps(dict(video='/media/studio.mp4',poster='/media/studio.jpg',vtt='/media/studio.vtt',duration=duration,language='en',review='preview; listening review pending',sha256=hashlib.sha256((media/'studio.mp4').read_bytes()).hexdigest()),indent=2),encoding='utf-8');print('Studio helper film:',duration,'seconds')
