"""Local behavioral tests: tone fixtures establish timing/failure semantics, not speech quality."""
import importlib.util
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
import io
import os
import urllib.error
import subprocess
from unittest import mock
from unittest.mock import patch
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import studio_speech
from voice import synthesize,compose
from qa import compare,inspect,spoken_script
from studio import build
from render import prepare,render,probe


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for i,seconds in enumerate([.4,.7]):
            with wave.open(str(self.root/f'{i}.wav'),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000)
                w.writeframes(b''.join(struct.pack('<h',round(5000*math.sin(n*2*math.pi*300/48000)))for n in range(round(seconds*48000))))
        self.text=self.root/'text.txt';self.text.write_text('Exact test phrase.',encoding='utf-8')
        self.cfg=self.root/'config.json'

    def tearDown(self):self.tmp.cleanup()

    def config(self,command):
        cfg=dict(provider='synthetic-test',model='tone-fixture',revision='1',network='none',languages=['en'],voices=['fixture'],command=command)
        self.cfg.write_text(json.dumps(cfg),encoding='utf-8');return cfg

    def test_unsupported_language_never_invokes_provider(self):
        marker=self.root/'invoked'
        self.config([sys.executable,'-c',f"open({str(marker)!r},'w').write('bad')",'{input}','{output}'])
        with self.assertRaisesRegex(ValueError,'unsupported'):synthesize(self.cfg,self.text,self.root/'out.wav','ar','fixture')
        self.assertFalse(marker.exists())

    def test_provider_failure_has_no_fallback_or_partial_output(self):
        self.config([sys.executable,'-c','raise SystemExit(9)','{input}','{output}'])
        with self.assertRaisesRegex(ValueError,'no fallback'):synthesize(self.cfg,self.text,self.root/'out.wav','en','fixture')
        self.assertFalse((self.root/'out.wav').exists())

    def test_explicit_provider_audio_and_identity_no_overwrite(self):
        self.config([sys.executable,'-c',f"import shutil,sys;shutil.copyfile({str(self.root/'0.wav')!r},sys.argv[2])",'{input}','{output}'])
        out=self.root/'out.wav';receipt=synthesize(self.cfg,self.text,out,'en','fixture')
        self.assertEqual(receipt['voice'],'fixture');self.assertEqual(receipt['language'],'en')
        self.assertEqual(out.read_bytes(),(self.root/'0.wav').read_bytes())
        with self.assertRaisesRegex(ValueError,'exists'):synthesize(self.cfg,self.text,out,'en','fixture')

    def test_phrase_boundaries_follow_audio_duration(self):
        spec=self.root/'phrases.json';spec.write_text(json.dumps({'phrases':[{'audio':'0.wav','text':'First phrase.'},{'audio':'1.wav','text':'Second phrase.'}]}),encoding='utf-8')
        result=compose(spec,self.root/'composed')
        self.assertAlmostEqual(result['captions'][1]['start'],.4,places=5)
        self.assertAlmostEqual(result['captions'][1]['end'],1.1,places=5)
        self.assertAlmostEqual(float(probe(self.root/'composed/narration.wav')['format']['duration']),1.1,places=4)

    def test_order_negations_numbers_and_duplicates_are_not_lost(self):
        for a,b in [('Do not send it.','Do send it.'),('Send two files.','Send three files.'),('Click save then close.','Click close then save.'),('Go go now.','Go now.')]:
            self.assertFalse(compare(a,b)['exactOrderedMatch'])
        self.assertTrue(compare('Save the file.','save the file!')['exactOrderedMatch'])

    def test_studio_client_uses_server_resolved_english_reference(self):
        reference_hash='f'*64
        status={'config':{'engine':'omnivoice','voice':'mine','profileReady':True,'languages':['en','ar'],'references':{},'accepted':{'ar':{'engine':'omnivoice','referenceSha256':reference_hash}}},'engines':{'omnivoice':{'langs':['en','ar']}},'mine':{'en':{'sha256':reference_hash}},'effectiveReferences':{'en':'en','ar':'en'},'plan':{'models':[{'id':'omnivoice','repo':'synthetic-test/voice','revision':'test'}]}}
        posts=[]
        def response(request,timeout):
            if isinstance(request,str):return io.BytesIO(json.dumps(status).encode())
            posts.append(json.loads(request.data));audio=io.BytesIO(b'synthetic-provider-response')
            audio.headers={'X-Voice':'omnivoice; cloned=True; lang=ar','X-Voice-Reference-SHA256':reference_hash,'X-Voice-Reference-Language':'en'}
            return audio
        def convert(args):Path(args[-1]).write_bytes((self.root/'0.wav').read_bytes())
        with patch.object(studio_speech.urllib.request,'urlopen',response),patch.object(studio_speech,'command',convert):
            receipt=studio_speech.generate(self.text,self.root/'accepted-ar.wav','ar')
        self.assertEqual(receipt['referenceLanguage'],'en');self.assertEqual(receipt['referenceSha256'],reference_hash)
        self.assertEqual(posts,[{'input':'Exact test phrase.','language':'ar','engine':'omnivoice','mine':True}])
        self.assertEqual((self.root/'accepted-ar.wav').read_bytes(),(self.root/'0.wav').read_bytes())
    def test_studio_client_honors_explicit_english_reference_grant_without_fake_ar_approval(self):
        reference_hash='e'*64
        status={'config':{'engine':'omnivoice','voice':'mine','profileReady':True,'languages':['en','ar'],'accepted':{'en':{'id':'real-English','engine':'omnivoice','referenceSha256':reference_hash}},'sharedEnglishApproval':{'mode':'english-reference','engine':'omnivoice','referenceSha256':reference_hash,'acceptedEnglishId':'real-English'}},'engines':{'omnivoice':{'langs':['en','ar']}},'mine':{'en':{'sha256':reference_hash}},'effectiveReferences':{'en':'en','ar':'en'},'plan':{'models':[{'id':'omnivoice','repo':'synthetic-test/voice','revision':'test'}]}}
        calls=[]
        def response(request,timeout):
            if isinstance(request,str):return io.BytesIO(json.dumps(status).encode())
            calls.append(json.loads(request.data));audio=io.BytesIO(b'fixture');audio.headers={'X-Voice':'omnivoice; cloned=True; lang=ar','X-Voice-Reference-SHA256':reference_hash,'X-Voice-Reference-Language':'en'};return audio
        def convert(args):Path(args[-1]).write_bytes((self.root/'0.wav').read_bytes())
        with patch.object(studio_speech.urllib.request,'urlopen',response),patch.object(studio_speech,'command',convert):
            receipt=studio_speech.generate(self.text,self.root/'shared-ar.wav','ar')
        self.assertEqual(receipt['approvalScope'],'english-reference');self.assertEqual(receipt['referenceLanguage'],'en');self.assertNotIn('ar',status['config']['accepted'])
        status['config']['sharedEnglishApproval']['acceptedEnglishId']='stale'
        with patch.object(studio_speech.urllib.request,'urlopen',response),patch.object(studio_speech,'command',convert):
            with self.assertRaisesRegex(ValueError,'Accept a fresh'):studio_speech.generate(self.text,self.root/'refused.wav','ar')
        self.assertEqual(len(calls),1);self.assertFalse((self.root/'refused.wav').exists())
    def test_english_digits_compare_as_the_spoken_words(self):
        heard='We made over 2,000 commits; 71% landed in 3.5 weeks.'
        self.assertTrue(compare('We made over two thousand commits; seventy-one percent landed in three point five weeks.',heard,'en')['exactOrderedMatch'])
        self.assertFalse(compare('Send two files.','Send 3 files.','en')['exactOrderedMatch'])
        self.assertFalse(compare('Send two thousand files.','Send 2,000 files.')['exactOrderedMatch'],'Other languages keep digits literal')

    def test_landscape_export_gets_a_landscape_contact_sheet(self):
        from PIL import Image
        Image.new('RGB',(640,360),'#335566').save(self.root/'still.png')
        plan=dict(version=1,width=640,height=360,fps=30,voice=dict(provider='test',model='tone-fixture',revision='1',name='not-speech',language='en'),
                  scenes=[dict(kind='still',status='demonstration',title='Hold',visual='still.png',audio='1.wav',say='Synthetic tone.',captions=[dict(start=0,end=.7,text='Synthetic tone.')])])
        (self.root/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        render(self.root/'plan.json',self.root/'cut')
        inspect(self.root/'cut/walkthrough.mp4',self.root/'cut/evidence.json',self.root/'qa')
        with Image.open(self.root/'qa/contact-sheet.jpg') as sheet:self.assertGreater(sheet.width,sheet.height)

    def test_audition_escapes_content_and_keeps_audio(self):
        spec=self.root/'audition.json';spec.write_text(json.dumps({'takes':[dict(name='<unsafe>',provider='test',model='tone',revision='1',language='en',text='Synthetic tone, not speech.',audio='0.wav')]}),encoding='utf-8')
        out=self.root/'studio';build(spec,out)
        text=(out/'index.html').read_text(encoding='utf-8')
        self.assertIn('&lt;unsafe&gt;',text);self.assertNotIn('<unsafe>',text)
        self.assertEqual((out/'take-0.wav').read_bytes(),(self.root/'0.wav').read_bytes())

    def test_numbered_speech_survives_and_only_scene_headings_are_dropped(self):
        narration='1. Sign up\n1. Create your account. 2. Confirm your email.\n\n2. Done\nThat is all.\n'
        self.assertEqual(spoken_script(narration,['Sign up','Done']),'1. Create your account. 2. Confirm your email.\n\nThat is all.')

    def test_a_sign_before_a_number_is_never_dropped(self):
        self.assertFalse(compare('The balance is -50 dollars.','The balance is 50 dollars.','en')['exactOrderedMatch'])
        self.assertTrue(compare('The balance is minus fifty dollars.','The balance is −50 dollars.','en')['exactOrderedMatch'])
        self.assertFalse(compare('Balance -50.','Balance 50.')['exactOrderedMatch'],'Literal digits keep their sign too')
        self.assertTrue(compare('Weeks three five, COVID nineteen.','Weeks 3-5, COVID-19.','en')['exactOrderedMatch'],'A hyphen inside a token is not a minus')

    def test_combining_marks_stay_in_their_word(self):
        for a,b in [('कि','की'),('กิน','กัน')]:
            self.assertFalse(compare(a,b)['exactOrderedMatch'],f'{a} and {b} differ by a vowel sign')
            self.assertEqual(len(compare(a,a)['changes']),0)
        self.assertTrue(compare('مَرْحَبًا بِكُمْ','مرحبا بكم','ar')['exactOrderedMatch'],'Arabic harakat are dropped on both sides on purpose')
        self.assertFalse(compare('مرحبا بكم','مرحبا بهم','ar')['exactOrderedMatch'],'Arabic letters still count')


def studio_state(**config):
    c=dict(engine='omnivoice',voice='mine',profileReady=True,languages=['en'],references={},accepted={'en':dict(engine='omnivoice',referenceSha256='abc')})
    c.update(config)
    return dict(config=c,engines={'omnivoice':dict(langs=['en','ar'])},mine={'en':dict(sha256='abc')})


class StudioStatusTests(unittest.TestCase):
    def test_an_accepted_profile_is_ready(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state()):
            r=studio_speech.status()
        self.assertTrue(r['running']);self.assertTrue(r['ready']);self.assertEqual(r['languages'],{'en':dict(ready=True)})

    def test_a_language_without_an_audition_says_what_the_user_must_do(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state()):
            r=studio_speech.status(['en','ar'])
        self.assertFalse(r['ready']);self.assertTrue(r['languages']['en']['ready'])
        self.assertIn('Add this language',r['languages']['ar']['reason']);self.assertIn('do not operate the page',r['next'])

    def test_a_studio_that_is_not_running_is_reported_not_raised(self):
        with mock.patch.object(studio_speech,'fetch_status',side_effect=urllib.error.URLError('refused')):
            r=studio_speech.status()
        self.assertFalse(r['running']);self.assertFalse(r['ready'])

    def test_wait_polls_until_the_user_finishes(self):
        states=[studio_state(profileReady=False),studio_state()]
        with mock.patch.object(studio_speech,'fetch_status',side_effect=states):
            r=studio_speech.status(wait=5,poll=0)
        self.assertTrue(r['ready'])

    def test_status_refuses_a_remote_endpoint(self):
        with self.assertRaises(ValueError):studio_speech.status(endpoint='http://example.com:8765')

    def test_start_launches_a_stopped_studio_in_the_background(self):
        with tempfile.TemporaryDirectory()as d,mock.patch.object(studio_speech,'DATA',Path(d)),\
             mock.patch.object(studio_speech,'fetch_status',side_effect=[urllib.error.URLError('refused'),studio_state()]),\
             mock.patch.object(studio_speech,'studio_python',return_value=sys.executable),\
             mock.patch.object(studio_speech.subprocess,'Popen')as popen:
            st=studio_speech.start_server('http://127.0.0.1:9911')
        self.assertTrue(st['config']['profileReady'])
        args,kw=popen.call_args
        self.assertEqual(args[0][1],str(studio_speech.STUDIO));self.assertEqual(kw['env']['VOICE_STUDIO_PORT'],'9911');self.assertTrue(kw['start_new_session'])
        self.assertNotIn('cwd',kw);self.assertEqual(kw['env']['NARRATE_VIDEO_DATA'],str(Path(d).absolute()))

    def test_a_relative_data_folder_reaches_the_studio_as_an_absolute_path(self):
        with tempfile.TemporaryDirectory()as d:
            cwd=os.getcwd();os.chdir(d)
            try:
                with mock.patch.object(studio_speech,'DATA',Path('studio-data')),mock.patch.dict(studio_speech.os.environ,{'NARRATE_VIDEO_PYTHON':'env/bin/python'}),\
                     mock.patch.object(studio_speech,'fetch_status',side_effect=[urllib.error.URLError('refused'),studio_state()]),\
                     mock.patch.object(studio_speech.subprocess,'Popen')as popen:
                    studio_speech.start_server()
                args,kw=popen.call_args
                self.assertEqual(kw['env']['NARRATE_VIDEO_DATA'],str(Path.cwd()/'studio-data'))
                self.assertEqual(args[0][0],str(Path.cwd()/'env/bin/python'))
            finally:os.chdir(cwd)

    def test_a_running_studio_is_not_started_again(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state()),mock.patch.object(studio_speech.subprocess,'Popen')as popen:
            r=studio_speech.status(start=True)
        self.assertTrue(r['ready']);popen.assert_not_called()

    def test_a_studio_that_never_starts_says_where_the_log_is(self):
        with tempfile.TemporaryDirectory()as d,mock.patch.object(studio_speech,'DATA',Path(d)),\
             mock.patch.object(studio_speech,'fetch_status',side_effect=urllib.error.URLError('refused')),\
             mock.patch.object(studio_speech,'studio_python',return_value=sys.executable),mock.patch.object(studio_speech.subprocess,'Popen'):
            with self.assertRaisesRegex(RuntimeError,'studio.log'):studio_speech.start_server(timeout=0)

    def test_accepted_auditions_without_saving_ask_only_for_the_save(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state(profileReady=False)):
            r=studio_speech.status()
        self.assertFalse(r['ready']);self.assertIn('Save my voice profile',r['languages']['en']['reason'])
        missing=studio_state(profileReady=False,accepted={})
        with mock.patch.object(studio_speech,'fetch_status',return_value=missing):
            self.assertIn('accept your voice auditions',studio_speech.status()['languages']['en']['reason'])

    def test_open_shows_the_studio_once_and_only_when_setup_is_needed(self):
        states=[studio_state(profileReady=False),studio_state(profileReady=False),studio_state()]
        # open_studio is mocked so this holds on headless hosts; its browser behavior has its own tests.
        with mock.patch.object(studio_speech,'fetch_status',side_effect=states),mock.patch.object(studio_speech,'open_studio',return_value=True)as browser:
            r=studio_speech.status(wait=5,poll=0,show=True)
        self.assertTrue(r['ready']);browser.assert_called_once_with('http://127.0.0.1:8765')
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state()),mock.patch.object(studio_speech,'open_studio')as browser:
            self.assertTrue(studio_speech.status(show=True)['ready'])
        browser.assert_not_called()

    def test_without_open_no_browser_is_claimed(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state(profileReady=False)),mock.patch.object(studio_speech.webbrowser,'open')as browser:
            r=studio_speech.status()
        browser.assert_not_called();self.assertNotIn('opened',r)
        self.assertIn('Give the user the studio link',r['next']);self.assertNotIn('is open in their browser',r['next'])

    def test_linux_without_a_display_never_launches_a_console_browser(self):
        env={k:v for k,v in studio_speech.os.environ.items() if k not in('DISPLAY','WAYLAND_DISPLAY')}
        with mock.patch.object(studio_speech.sys,'platform','linux'),mock.patch.dict(studio_speech.os.environ,env,clear=True),mock.patch.object(studio_speech.webbrowser,'open')as browser:
            self.assertFalse(studio_speech.open_studio('http://127.0.0.1:8765'))
        browser.assert_not_called()
        with mock.patch.object(studio_speech.sys,'platform','linux'),mock.patch.dict(studio_speech.os.environ,{'DISPLAY':':0'}),mock.patch.object(studio_speech.webbrowser,'open',return_value=True)as browser:
            self.assertTrue(studio_speech.open_studio('http://127.0.0.1:8765'))

    def test_open_studio_uses_the_default_browser_in_a_new_tab(self):
        with mock.patch.dict(studio_speech.os.environ,{'DISPLAY':':0'}),mock.patch.object(studio_speech.webbrowser,'open',return_value=True)as browser:
            self.assertTrue(studio_speech.open_studio('http://127.0.0.1:8765'))
        browser.assert_called_once_with('http://127.0.0.1:8765',new=2)

    def test_without_a_browser_the_user_gets_the_link(self):
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state(profileReady=False)),mock.patch.object(studio_speech.webbrowser,'open',return_value=False):
            r=studio_speech.status(show=True)
        self.assertFalse(r['opened']);self.assertIn('open in their own browser',r['next'])

    def test_stop_ends_the_studio_and_waits_for_it(self):
        running=dict(studio_state(),pid=4321,setup=dict(state='ready'))
        with mock.patch.object(studio_speech,'fetch_status',side_effect=[running,running,urllib.error.URLError('refused')]),\
             mock.patch.object(studio_speech,'is_studio',return_value=True),mock.patch.object(studio_speech.os,'kill')as kill,\
             mock.patch.object(studio_speech.time,'sleep'):
            r=studio_speech.stop()
        kill.assert_called_once_with(4321,studio_speech.signal.SIGTERM);self.assertTrue(r['stopped']);self.assertFalse(r['running'])

    def test_stop_is_a_no_op_when_the_studio_is_not_running(self):
        with mock.patch.object(studio_speech,'fetch_status',side_effect=urllib.error.URLError('refused')),mock.patch.object(studio_speech.os,'kill')as kill:
            r=studio_speech.stop()
        kill.assert_not_called();self.assertFalse(r['stopped']);self.assertFalse(r['running'])

    def test_stop_refuses_during_setup_and_for_another_program(self):
        downloading=dict(studio_state(),pid=4321,setup=dict(state='downloading'))
        with mock.patch.object(studio_speech,'fetch_status',return_value=downloading),mock.patch.object(studio_speech.os,'kill')as kill:
            with self.assertRaisesRegex(ValueError,'setup is running'):studio_speech.stop()
        for state,studio in((dict(studio_state(),pid=4321),False),(studio_state(),True)):
            with mock.patch.object(studio_speech,'fetch_status',return_value=state),mock.patch.object(studio_speech,'is_studio',return_value=studio),\
                 mock.patch.object(studio_speech.os,'kill')as kill:
                with self.assertRaisesRegex(ValueError,'not a voice studio'):studio_speech.stop()
            kill.assert_not_called()

    @unittest.skipIf(studio_speech.os.name=='nt','process command lines are not checked on Windows')
    def test_is_studio_accepts_only_this_skills_studio(self):
        # This test runner's own command line does not run studio.py.
        self.assertFalse(studio_speech.is_studio(studio_speech.os.getpid()))
        wait='import time;time.sleep(30)'
        for argument,expected in(('studio.py',False),(str(studio_speech.STUDIO),True)):
            child=subprocess.Popen([sys.executable,'-c',wait,argument])
            try:self.assertEqual(studio_speech.is_studio(child.pid),expected,argument)
            finally:child.kill();child.wait()

    def test_stop_refuses_on_windows_where_the_process_cannot_be_checked(self):
        with mock.patch.object(studio_speech.os,'name','nt'):self.assertFalse(studio_speech.is_studio(studio_speech.os.getpid()))

    def test_the_default_model_is_not_reported_as_chosen_before_setup(self):
        fresh=studio_state(profileReady=False,accepted={});fresh['plan']=dict(recommended='chatterbox')
        with mock.patch.object(studio_speech,'fetch_status',return_value=fresh):r=studio_speech.status()
        self.assertIsNone(r['engine']);self.assertEqual(r['recommended'],'chatterbox')
        with mock.patch.object(studio_speech,'fetch_status',return_value=studio_state(profileReady=False,setupReady=True,setupModel='omnivoice')):
            r=studio_speech.status()
        self.assertEqual(r['engine'],'omnivoice');self.assertNotIn('recommended',r)


    def test_a_half_made_audio_env_says_to_recreate_it(self):
        with tempfile.TemporaryDirectory()as d:
            broken=Path(d)/'audio-env/bin/python';broken.parent.mkdir(parents=True)
            broken.write_text('#!/bin/sh\nexit 1\n');broken.chmod(0o755)
            with mock.patch.object(studio_speech,'DATA',Path(d)),mock.patch.dict(studio_speech.os.environ,{'NARRATE_VIDEO_PYTHON':''}),\
                 mock.patch.object(studio_speech,'fetch_status',side_effect=urllib.error.URLError('refused')):
                r=studio_speech.status(start=True)
        self.assertFalse(r['running'])
        self.assertIn('does not start',r['next']);self.assertIn('create it again',r['next'])



if __name__=='__main__':unittest.main()
