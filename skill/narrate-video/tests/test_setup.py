"""Behavioral setup-policy and local HTTP tests. No model download or GPU generation."""
import importlib.util,json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,wave,math,struct,hashlib
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/voice-studio';sys.path.insert(0,str(SCRIPTS))
# The policy tests describe the Apple Silicon catalog unless a test chooses another runtime.
os.environ['NARRATE_VIDEO_RUNTIME']='mlx'
from catalog import recommend,validate_languages,MODELS,LANGUAGES,installed
spec=importlib.util.spec_from_file_location('setup_server',SCRIPTS/'studio.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class CudaPolicyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.saved={k:os.environ.get(k)for k in('NARRATE_VIDEO_RUNTIME','HF_HUB_CACHE')}
  os.environ.update(NARRATE_VIDEO_RUNTIME='cuda',HF_HUB_CACHE=str(self.root/'hub'))
 def tearDown(self):
  for k,v in self.saved.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  self.tmp.cleanup()
 def test_nvidia_offers_only_models_with_a_cuda_build(self):
  plan=recommend(['en','ar'],self.root);self.assertEqual(plan['recommended'],'chatterbox');self.assertEqual(plan['runtime']['label'],'NVIDIA GPU · CUDA')
  c=next(x for x in plan['models']if x['id']=='chatterbox');self.assertEqual(c['repo'],'ResembleAI/chatterbox');self.assertEqual(c['bytes'],MODELS['chatterbox']['cuda']['bytes'])
  o=next(x for x in plan['models']if x['id']=='omnivoice');self.assertFalse(o['eligible']);self.assertIn('Apple Silicon',o['reason'])
 def test_gulf_arabic_has_no_nvidia_model_yet(self):self.assertIsNone(recommend(['afb'],self.root)['recommended'])
 def test_nvidia_chatterbox_is_found_complete_in_the_hugging_face_cache(self):
  c=MODELS['chatterbox']['cuda'];snap=self.root/'hub'/('models--'+c['repo'].replace('/','--'))/'snapshots'/c['revision'];snap.mkdir(parents=True)
  for f in c['files'][:-1]:(snap/f).write_bytes(b'fixture')
  self.assertFalse(installed('chatterbox',self.root))
  (snap/c['files'][-1]).write_bytes(b'fixture');self.assertTrue(installed('chatterbox',self.root))
  self.assertEqual(next(x for x in recommend(['en'],self.root)['models']if x['id']=='chatterbox')['downloadBytes'],0)

class PolicyTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_arabic_excludes_qwen_base(self):
  plan=recommend(['en','ar'],self.root)
  q=next(x for x in plan['models']if x['id']=='qwen3-base');self.assertFalse(q['eligible']);self.assertEqual(q['missing'],['ar'])
 def test_english_allows_qwen_cloning_checkpoint(self):
  q=next(x for x in recommend(['en'],self.root)['models']if x['id']=='qwen3-base');self.assertTrue(q['eligible']);self.assertTrue(q['cloning']);self.assertIn('Base',q['repo'])
 def test_gulf_arabic_coverage_changes_available_models(self):
  p=recommend(['afb'],self.root,'compact');self.assertEqual(p['recommended'],'omnivoice');self.assertEqual([x['id']for x in p['models']if x['eligible']],['omnivoice'])
 def test_compact_prefers_smaller_model_when_languages_fit(self):self.assertEqual(recommend(['en','ar'],self.root,'compact')['recommended'],'chatterbox')
 def test_current_installed_model_is_preferred_for_reuse(self):
  old=os.environ.pop('NARRATE_VIDEO_MODEL_DIR',None)
  try:
   for name in ['chatterbox','omnivoice']:
    p=self.root/'models'/name;p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture')
    if name=='omnivoice':(p/'audio_tokenizer').mkdir();(p/'audio_tokenizer/model.safetensors').write_bytes(b'fixture')
    else:
     d=MODELS[name]['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snap=cache/'snapshots'/d['revision'];snap.mkdir(parents=True);(snap/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'],encoding='utf-8')
   self.assertEqual(recommend(['en','ar'],self.root,'reuse','omnivoice')['recommended'],'omnivoice')
  finally:
   if old is not None:os.environ['NARRATE_VIDEO_MODEL_DIR']=old
 def test_chatterbox_requires_its_separate_tokenizer(self):
  p=self.root/'models/chatterbox';p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture')
  self.assertFalse(installed('chatterbox',self.root))
  d=MODELS['chatterbox']['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snapshot=cache/'snapshots'/d['revision'];snapshot.mkdir(parents=True);(snapshot/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'],encoding='utf-8')
  self.assertTrue(installed('chatterbox',self.root))
 def test_qwen_requires_its_speech_tokenizer(self):
  p=self.root/'models/qwen3-base';p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture');self.assertFalse(installed('qwen3-base',self.root))
 def test_invalid_language_and_empty_selection_fail(self):
  for codes in [[],['made-up'],['en']*13]:
   with self.assertRaises(ValueError):validate_languages(codes)
 def test_only_cloning_models_are_offered(self):self.assertTrue(all(m['cloning']for m in MODELS.values()))
 def test_every_language_has_a_bundled_flag(self):
  for l in LANGUAGES.values():self.assertTrue((SCRIPTS/'flags'/f"{l['flag']}.svg").is_file(),l['code'])

class HttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);server.DATA=self.root;server.VOICES=self.root/'voices/me';server.OUT=self.root/'out/studio';server.GUIDE=self.root/'out/guide';server.CONFIG=self.root/'config.json'
  for p in(server.VOICES,server.OUT):p.mkdir(parents=True)
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=self.http.server_address[1];self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{server.PORT}'
 def tearDown(self):self.http.shutdown();self.http.server_close();self.tmp.cleanup()
 def request(self,path,data=None,headers=None):
  payload=json.dumps(data).encode()if data is not None else None
  req=urllib.request.Request(self.url+path,data=payload,headers={'Content-Type':'application/json',**(headers or{})})
  try:
   with urllib.request.urlopen(req)as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   raw=e.read().decode()
   try:raw=json.loads(raw)
   except ValueError:pass
   return e.code,raw
 def test_preferences_persist_user_languages_without_model_swap(self):
  status,data=self.request('/api/preferences',{'languages':['en','ar'],'preference':'compact'});self.assertEqual(status,200);self.assertEqual(data['config']['engine'],'omnivoice');self.assertEqual(data['plan']['recommended'],'chatterbox')
 def test_studio_stylesheet_is_served_with_css_content_type(self):
  with urllib.request.urlopen(self.url+'/studio.css')as response:
   self.assertEqual(response.status,200);self.assertEqual(response.headers.get_content_type(),'text/css');self.assertIn(b'--coral',response.read())
 def test_private_status_rejects_foreign_origin(self):self.assertEqual(self.request('/api/status',headers={'Origin':'https://foreign.example'})[0],403)
 def test_invalid_setup_cannot_start_download(self):
  status,_=self.request('/api/setup',{'languages':['ar'],'model':'qwen3-base'});self.assertEqual(status,400);self.assertFalse((self.root/'models').exists())
 def test_setup_names_the_supported_runtimes_and_never_substitutes(self):
  try:
   os.environ['NARRATE_VIDEO_RUNTIME']='none'
   status,data=self.request('/api/setup',{'languages':['en'],'model':'chatterbox'});self.assertEqual(status,400);self.assertIn('Apple Silicon Mac, or an NVIDIA GPU',data['error'])
   os.environ['NARRATE_VIDEO_RUNTIME']='cuda'
   status,data=self.request('/api/setup',{'languages':['en'],'model':'omnivoice'});self.assertEqual(status,400);self.assertIn('not available for NVIDIA',data['error'])
  finally:os.environ['NARRATE_VIDEO_RUNTIME']='mlx'
  self.assertFalse((self.root/'models').exists())
 def test_every_language_flag_is_served_and_paths_cannot_escape(self):
  for code in {l['flag']for l in LANGUAGES.values()}:
   with urllib.request.urlopen(self.url+f'/flags/{code}.svg')as r:self.assertEqual(r.headers.get_content_type(),'image/svg+xml');self.assertIn(b'<svg',r.read(200))
  for path in('/flags/..%2Fstudio.py','/flags/gb.py','/guide/..%2F..%2Fconfig.json'):self.assertEqual(self.request(path)[0],404)
 def test_guide_needs_setup_and_a_saved_recording_and_is_never_an_audition(self):
  status,data=self.request('/api/guide',{'lang':'en','text':'Hello.'});self.assertEqual(status,400);self.assertIn('Complete setup',data['error'])
  server.save_config({'engine':'chatterbox','languages':['en','zh'],'setupReady':True,'setupModel':'chatterbox'})
  status,data=self.request('/api/guide',{'lang':'zh','text':'你好。'});self.assertEqual(status,400);self.assertIn('Save one recording',data['error'])
  status,data=self.request('/api/guide',{'lang':'fr','text':'Bonjour.'});self.assertEqual(status,400);self.assertIn('selected language',data['error'])
  self.assertEqual(list(server.OUT.glob('*')),[])
 def test_finish_requires_accepted_auditions(self):self.assertEqual(self.request('/api/finish',{})[0],400)
 def test_committed_english_is_an_automatic_nonwriting_default(self):
  (server.VOICES/'en.wav').write_bytes(b'fixture');server.save_config({'languages':['en','ar','es']})
  before=server.CONFIG.read_bytes();status,data=self.request('/api/status')
  self.assertEqual(status,200);self.assertEqual(data['effectiveReferences'],{'en':'en','ar':'en','es':'en'})
  self.assertEqual(server.CONFIG.read_bytes(),before);self.assertEqual(data['config']['references'],{})
  self.assertEqual(server.selected_reference('ar',{},server.config()),'en')
 def test_no_arbitrary_nonenglish_fallback_or_preset(self):
  (server.VOICES/'fr.wav').write_bytes(b'fixture');server.save_config({'languages':['ar'],'setupReady':True,'setupModel':'omnivoice'})
  status,data=self.request('/api/generate',{'engine':'omnivoice','lang':'ar','text':'test'})
  self.assertEqual(status,400);self.assertIn('Record English once',data['error'])
 def test_explicit_reference_overrides_default_and_missing_choice_refuses(self):
  for code in ['en','fr','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  server.save_config({'languages':['en','ar'],'references':{'ar':'fr'}})
  self.assertEqual(server.selected_reference('ar',{},server.config()),'fr')
  self.assertEqual(server.selected_reference('ar',{'reference':'en'},server.config()),'en')
  server.save_config({'references':{'ar':'de'}})
  with self.assertRaises(ValueError):server.selected_reference('ar',{},server.config())
 def test_own_legacy_recording_is_preserved_instead_of_english_default(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
 def test_reselecting_effective_reference_keeps_approved_profile(self):
  (server.VOICES/'en.wav').write_bytes(b'fixture')
  approved={'ar':{'id':'already-listened','engine':'omnivoice','referenceSha256':'fixture'}}
  server.save_config({'languages':['en','ar'],'accepted':approved,'profileReady':True})
  status,data=self.request('/api/reference-choice',{'language':'ar','reference':'en'})
  self.assertEqual(status,200);self.assertTrue(data['config']['profileReady']);self.assertEqual(data['config']['accepted'],approved)
 def test_explicit_override_changes_only_target_without_accepting_auditions(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  approved={'en':{'id':'already-listened','engine':'omnivoice'}}
  server.save_config({'languages':['en','ar','es'],'references':{'ar':'en'},'accepted':approved,'profileReady':True})
  status,data=self.request('/api/reference-choice',{'language':'ar','reference':'ar'})
  self.assertEqual(status,200);self.assertEqual(data['effectiveReferences'],{'en':'en','ar':'ar','es':'en'})
  self.assertEqual(data['config']['accepted'],approved);self.assertFalse(data['config']['profileReady'])
  self.assertEqual(data['config']['languages'],['en','ar','es']);self.assertEqual(data['config']['engine'],'omnivoice')
 def test_replaced_english_stales_followers_but_preserves_own_override(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(('before-'+code).encode())
  en_hash=server.sha(server.VOICES/'en.wav');ar_hash=server.sha(server.VOICES/'ar.wav')
  accepted={code:{'id':code+'-listened','engine':'omnivoice','referenceSha256':ar_hash if code=='ar' else en_hash} for code in ['en','ar','es']}
  server.save_config({'languages':['en','ar','es'],'references':{'ar':'ar'},'accepted':accepted,'profileReady':True})
  (server.VOICES/'en.wav').write_bytes(b'after-English');server.save_config({'profileReady':False})
  status,data=self.request('/api/finish',{});self.assertEqual(status,400)
  self.assertEqual(server.config()['accepted'],accepted)
  self.assertEqual(server.sha(server.VOICES/'ar.wav'),ar_hash)
  self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
  current=server.sha(server.VOICES/'en.wav')
  for code in ['en','es']:accepted[code]={**accepted[code],'id':'newly-listened-'+code,'referenceSha256':current}
  server.save_config({'accepted':accepted})
  self.assertEqual(self.request('/api/finish',{})[0],200)
  self.assertEqual(server.config()['accepted']['ar']['referenceSha256'],ar_hash)
 def test_explicit_shared_english_finishes_twelve_languages_without_fabricated_acceptance(self):
  codes=['en','ar','es','fr','de','it','pt','zh','ja','ko','hi','ru']
  for code in ['en','ar']:
   (server.VOICES/(code+'.wav')).write_bytes(('private-'+code).encode());(server.VOICES/(code+'.txt')).write_text('fixture-'+code)
  accepted={code:{'id':'listened-'+code,'engine':'omnivoice','referenceSha256':server.sha(server.VOICES/(code+'.wav')),'acceptedAt':'before'}for code in ['en','ar']}
  before={p.name:p.read_bytes()for p in server.VOICES.iterdir()}
  server.save_config({'languages':codes,'references':{'ar':'ar'},'accepted':accepted,'setupReady':True,'setupModel':'omnivoice'})
  status,data=self.request('/api/use-english-for-all',{});self.assertEqual(status,200)
  self.assertEqual(data['config']['languages'],codes);self.assertEqual(data['config']['accepted'],accepted)
  self.assertEqual(data['effectiveReferences'],{code:'en'for code in codes});self.assertTrue(data['config']['profileReady'])
  grant=data['config']['sharedEnglishApproval'];self.assertEqual(grant['acceptedEnglishId'],accepted['en']['id']);self.assertEqual(grant['referenceSha256'],accepted['en']['referenceSha256'])
  self.assertEqual(data['effectiveApprovals']['fr']['scope'],'english-reference')
  self.assertEqual({p.name:p.read_bytes()for p in server.VOICES.iterdir()},before)
  self.assertEqual(self.request('/api/finish',{})[0],200)
  # An own-language override loses inherited English approval until it has its own real approval.
  (server.VOICES/'fr.wav').write_bytes(b'new-french');(server.VOICES/'fr.txt').write_text('French fixture')
  self.assertEqual(self.request('/api/reference-choice',{'language':'fr','reference':'fr'})[0],200)
  self.assertEqual(self.request('/api/finish',{})[0],400)
  self.assertEqual(server.config()['accepted'],accepted)
 def test_shared_english_refuses_missing_stale_or_wrong_engine_approval_without_writing(self):
  (server.VOICES/'en.wav').write_bytes(b'current');(server.VOICES/'en.txt').write_text('fixture')
  for approval in [None,{'id':'old','engine':'omnivoice','referenceSha256':'stale'},{'id':'other','engine':'chatterbox','referenceSha256':server.sha(server.VOICES/'en.wav')}]:
   server.save_config({'languages':['en','ar'],'setupReady':True,'setupModel':'omnivoice','accepted':{'en':approval}if approval else{}});before=server.CONFIG.read_bytes()
   self.assertEqual(self.request('/api/use-english-for-all',{})[0],400);self.assertEqual(server.CONFIG.read_bytes(),before)
 def test_replaced_english_or_changed_engine_stales_shared_grant(self):
  (server.VOICES/'en.wav').write_bytes(b'original');(server.VOICES/'en.txt').write_text('fixture')
  accepted={'en':{'id':'approved-en','engine':'omnivoice','referenceSha256':server.sha(server.VOICES/'en.wav')}}
  server.save_config({'languages':['en','ar'],'setupReady':True,'setupModel':'omnivoice','accepted':accepted})
  self.assertEqual(self.request('/api/use-english-for-all',{})[0],200)
  original=server.config()['sharedEnglishApproval'];(server.VOICES/'en.wav').write_bytes(b'replaced')
  self.assertEqual(self.request('/api/finish',{})[0],400)
  self.assertEqual(server.config()['sharedEnglishApproval'],original);self.assertEqual(server.config()['accepted'],accepted)
  (server.VOICES/'en.wav').write_bytes(b'original');server.save_config({'engine':'chatterbox'})
  self.assertEqual(self.request('/api/finish',{})[0],400)
 def test_recording_replacement_preserves_previous_audio(self):
  from io import BytesIO
  def audio(freq):
   buf=BytesIO()
   with wave.open(buf,'wb')as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*freq*i/24000)))for i in range(24000*4)))
   return buf.getvalue()
  def upload(freq,lang='en'):
   req=urllib.request.Request(self.url+f'/api/reference?lang={lang}&text=Synthetic%20test%20fixture',data=audio(freq),headers={'Content-Type':'audio/wav'})
   with urllib.request.urlopen(req)as r:return json.load(r)
  server.save_config({'languages':['en','ar','es'],'accepted':{'es':{'id':'existing-approval'}}})
  upload(300);self.assertEqual(server.selected_reference('ar',{},server.config()),'en');old=server.sha(server.VOICES/'en.wav');upload(450);self.assertNotEqual(server.sha(server.VOICES/'en.wav'),old)
  history=list((self.root/'voice-history').rglob('en.wav'));self.assertEqual(len(history),1);self.assertEqual(server.sha(history[0]),old)
  self.assertEqual(server.selected_reference('ar',{},server.config()),'en')
  self.assertEqual(server.config()['accepted'],{'es':{'id':'existing-approval'}})
  upload(600,'ar');self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
  self.assertEqual(server.selected_reference('es',{},server.config()),'en')
  self.assertEqual(server.config()['references'],{'en':'en','ar':'ar'})
  self.assertEqual(server.config()['languages'],['en','ar','es'])

if __name__=='__main__':unittest.main()
