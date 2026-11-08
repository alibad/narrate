"""Selected-model practice uses no user reference, OS speech or provider fallback."""
import importlib.util,json,sys,tempfile,threading,unittest,urllib.request,wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/voice-studio';sys.path.insert(0,str(SCRIPTS))
import pronunciation,engines
spec=importlib.util.spec_from_file_location('pronunciation_server',SCRIPTS/'studio.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class PronunciationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.languages={'fr':{'code':'fr','omni_id':'fr'},'en':{'code':'en','omni_id':'en'}}
  self.config={'engine':'omnivoice','languages':['fr'],'setupReady':True,'setupModel':'omnivoice','references':{'en':'never-read'},'accepted':{'en':{'id':'unchanged'}},'profileReady':False}
  self.before=json.dumps(self.config,sort_keys=True)
  self.patches=[patch.object(pronunciation,'runtime',return_value='mlx'),patch.object(pronunciation,'installed',return_value=True)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in self.patches:p.stop()
  self.tmp.cleanup()
 def fake_speak(self,name,lang,text,out,data):
  self.assertEqual(name,self.config['engine']);self.assertEqual(lang,'fr')
  with wave.open(str(out),'wb')as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\xe8\x03'*2400)
  v=pronunciation.variant(name)
  return dict(engine=name,label=v['label'],model=v['repo'],revision=v['revision'],language=lang,seconds=.1,cloned=False,provider='local',fallback=False)
 def generate(self,request=None):return pronunciation.synthesize(({'lang':'fr','text':'Bonjour.','engine':'omnivoice'} if request is None else request),self.languages,self.config,self.root,self.root/'out')
 def test_capability_uses_the_selected_model_without_system_voice_inventory(self):
  c=pronunciation.capabilities(self.languages,self.config,self.root)['fr']
  self.assertTrue(c['available']);self.assertEqual(c['engine'],'omnivoice');self.assertEqual(c['provider'],'local');self.assertEqual(c['locale'],'fr')
  self.assertIn('OmniVoice',c['voice']);self.assertFalse(c['cloned'])
 def test_unsupported_selected_model_never_substitutes_omnivoice_or_os_speech(self):
  for name in ['chatterbox','qwen3-base','unknown']:
   self.config['engine']=name
   with patch.object(pronunciation,'speak_example')as speak:
    with self.assertRaisesRegex(ValueError,'No other|no other'):self.generate({'lang':'fr','text':'Bonjour.'})
    speak.assert_not_called();self.assertFalse((self.root/'out').exists())
 def test_incomplete_setup_or_missing_weights_refuses_without_generation(self):
  for key,value in [('setupReady',False),('setupModel','chatterbox')]:
   c=dict(self.config);c[key]=value
   with patch.object(pronunciation,'speak_example')as speak:
    self.assertFalse(pronunciation.capabilities(self.languages,c,self.root)['fr']['available']);speak.assert_not_called()
  with patch.object(pronunciation,'installed',return_value=False):self.assertFalse(pronunciation.capability(self.languages['fr'],self.config,self.root)['available'])
 def test_invalid_unselected_or_changed_model_refuses_before_outputs(self):
  for req in [[],{'lang':'en','text':'hello'},{'lang':['fr'],'text':'hello'},{'lang':'fr','text':''},{'lang':'fr','text':'x'*601},{'lang':'fr','text':'x\0y'},{'lang':'fr','text':[]},{'lang':'fr','text':'Bonjour','engine':'chatterbox'}]:
   with patch.object(pronunciation,'speak_example')as speak:
    with self.assertRaises(ValueError):self.generate(req)
    speak.assert_not_called();self.assertFalse((self.root/'out').exists())
 def test_selected_model_receipt_private_unique_outputs_no_profile_changes(self):
  with patch.object(pronunciation,'speak_example',side_effect=self.fake_speak)as speak,patch('subprocess.run',side_effect=AssertionError('OS speech is forbidden')):
   a=self.generate();b=self.generate()
  self.assertEqual(speak.call_count,2);self.assertNotEqual(a['url'],b['url']);self.assertEqual(a['engine'],'omnivoice');self.assertFalse(a['audition']);self.assertFalse(a['cloned'])
  self.assertEqual(json.dumps(self.config,sort_keys=True),self.before)
  self.assertEqual((self.root/'out'/Path(a['url']).name).stat().st_mode&0o777,0o600)
 def test_busy_failure_and_wrong_model_receipts_never_publish_final_audio(self):
  with pronunciation.LOCK,patch.object(pronunciation,'speak_example')as speak:
   with self.assertRaisesRegex(ValueError,'Another pronunciation'):self.generate()
   speak.assert_not_called()
  with patch.object(pronunciation,'speak_example',side_effect=RuntimeError('model failed')):
   with self.assertRaisesRegex(RuntimeError,'model failed'):self.generate()
  def wrong(*args):r=self.fake_speak(*args);r['engine']='other';return r
  with patch.object(pronunciation,'speak_example',side_effect=wrong):
   with self.assertRaisesRegex(ValueError,'did not match'):self.generate()
  self.assertEqual(list((self.root/'out').iterdir()),[]);self.assertTrue(pronunciation.LOCK.acquire(blocking=False));pronunciation.LOCK.release()
 def test_engine_runs_selected_model_unconditioned_on_its_serial_worker(self):
  import numpy as np
  seen={}
  class Model:
   def generate(inner,**kw):seen.update(kw);seen['thread']=threading.current_thread().name;yield SimpleNamespace(audio=np.full(2400,.1),sample_rate=24000)
  with patch.object(engines,'runtime',return_value='mlx'),patch.object(engines,'_load',return_value=Model())as load:
   r=engines.speak_example('omnivoice','fr','Bonjour.',str(self.root/'example.wav'),self.root)
  load.assert_called_once_with('omnivoice',self.root);self.assertEqual(seen['language'],'fr');self.assertIsNone(seen['ref_audio']);self.assertIsNone(seen['ref_text']);self.assertTrue(seen['thread'].startswith('voice-inference'));self.assertFalse(r['cloned']);self.assertFalse(r['fallback'])
 def test_actual_http_example_keeps_config_references_and_auditions_exact(self):
  keys=['DATA','VOICES','OUT','GUIDE','CONFIG','PORT'];saved={k:getattr(server,k)for k in keys}
  server.DATA=self.root;server.VOICES=self.root/'voices';server.OUT=self.root/'out/studio';server.GUIDE=self.root/'out/guide';server.CONFIG=self.root/'config.json';server.VOICES.mkdir();server.OUT.mkdir(parents=True)
  server.save_config(self.config);reference=server.VOICES/'en.wav';reference.write_bytes(b'private-fixture');before=server.CONFIG.read_bytes()
  http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=http.server_address[1];threading.Thread(target=http.serve_forever,daemon=True).start()
  try:
   with patch.dict(server.LANGUAGES,self.languages),patch.object(server,'references',return_value={}),patch.object(server,'recommend',return_value={}),patch.object(pronunciation,'speak_example',side_effect=self.fake_speak):
    base=f'http://127.0.0.1:{server.PORT}'
    with urllib.request.urlopen(base+'/api/status')as response:self.assertEqual(json.load(response)['pronunciation']['fr']['engine'],'omnivoice')
    req=urllib.request.Request(base+'/api/pronunciation',data=json.dumps({'lang':'fr','text':'Bonjour.','engine':'omnivoice'}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req)as response:r=json.load(response)
    with urllib.request.urlopen(base+r['url'])as response:self.assertTrue(response.read().startswith(b'RIFF'))
   self.assertEqual(server.CONFIG.read_bytes(),before);self.assertEqual(reference.read_bytes(),b'private-fixture');self.assertEqual(list(server.OUT.glob('*.json')),[])
  finally:
   http.shutdown();http.server_close()
   for key,value in saved.items():setattr(server,key,value)
if __name__=='__main__':unittest.main()
