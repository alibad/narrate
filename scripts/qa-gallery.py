"""Decode final exports, transcribe supported languages locally, and measure audio."""
from pathlib import Path
import sys,json,subprocess,os
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'skill/narrate-video/scripts';sys.path.insert(0,str(SCRIPTS));import qa
films=json.loads((ROOT/'content/gallery.json').read_text());supported=dict(en='English',zh='Chinese',hi='Hindi',es='Spanish',ar='Arabic',fr='French',pt='Portuguese',id='Indonesian')
summary=[]
for film in films:
 code=film['id'];folder=ROOT/'production'/code;cut=folder/('cut-2'if code=='ar'else'cut-1');transcript=folder/'final-transcript.txt'
 if code in supported and not transcript.exists():
  audio=folder/'final-decoded-audio.wav'
  subprocess.run(['ffmpeg','-v','error','-i',str(cut/'walkthrough.mp4'),'-vn','-ac','1','-ar','16000',str(audio)],check=True)
  result=subprocess.run([os.environ.get('LOCAL_AI_BIN','local-ai'),'transcribe',str(audio),'--language',supported[code],'--out',str(transcript)],capture_output=True,text=True)
  if result.returncode: (folder/'transcription-error.txt').write_text(result.stderr);print(code,'ASR failed; manual review pending',flush=True)
 report=qa.inspect(cut/'walkthrough.mp4',cut/'evidence.json',folder/'qa-1',transcript if transcript.exists()else None)
 summary.append(dict(language=code,decode=report['decode'],loudness=report['loudness'],transcript=report['audioTranscript'],manualReview='pending',asrCoverage='supported'if code in supported else'not supported by installed Qwen ASR; fluent review required'))
 print(code,'decode passed; LUFS',report['loudness']['input_i'],'ASR',isinstance(report['audioTranscript'],dict),flush=True)
 (ROOT/'production/qa-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
