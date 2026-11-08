import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';

// Execute the shipped inline client with a bounded synthetic DOM. Nothing in
// this suite can open a microphone, run speech inference or contact a server.
const html=await readFile(new URL('../scripts/voice-studio/studio.html',import.meta.url),'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const calls=[],events=[],listeners={},elements=new Map(),audio=[];
const node=()=>({innerHTML:'',outerHTML:'',value:'',textContent:'',hidden:false,focus(){},scrollIntoView(){},animate(){}});
const nativePlayer={pause(){events.push('native-pause')},play(){events.push('native-play');return Promise.resolve()},currentTime:0};
const reference={language:'en',name:'English',url:'/me/en.wav',seconds:5,sha256:'synthetic-english'};
const state={
 config:{engine:'omnivoice',languages:['en','ar'],preference:'reuse',setupReady:true,setupModel:'omnivoice',references:{},accepted:{en:{id:'accepted-en',engine:'omnivoice',referenceSha256:reference.sha256}},profileReady:false},
 effectiveReferences:{en:'en',ar:'en'},mine:{en:reference},
 languages:[{code:'en',name:'English',native:'English',prompt:'Full English passage.',sample:'English audition.',pronunciation:{latin:'FULL ING-glish PASS-ij.',note:'Approximate fixture.'},samplePronunciation:{latin:'ING-glish aw-DISH-un.',note:'Approximate sample.'}},{code:'ar',name:'Arabic',native:'العربية',rtl:true,prompt:'نص كامل.',sample:'اختبار.',pronunciation:{latin:'Naṣṣ kāmil.',note:'Approximate fixture.'},samplePronunciation:{latin:'Ikhtibār.',note:'Approximate sample.'}}],
 pronunciation:{en:{available:true,voice:'Fixture English',locale:'en-US'},ar:{available:true,voice:'Fixture Arabic',locale:'ar-SA'}},
 plan:{models:[{id:'omnivoice',label:'Synthetic model',languages:['en','ar'],installed:true,downloadBytes:0}]},setup:{state:'idle'},auditions:{}
};
let nextNative=null;
const context=vm.createContext({
 console,URL,URLSearchParams,setTimeout:()=>1,clearTimeout(){},
 document:{querySelectorAll(selector){return selector==='audio'?audio:[]},querySelector(selector){
  if(selector==='#native-player')return nativePlayer;
  if(['#wave','#reference-wave','#reference-player','#guide-player'].includes(selector))return null;
  if(!elements.has(selector))elements.set(selector,node());return elements.get(selector);
 },addEventListener(name,handler){listeners[name]=handler}},
 window:{scrollTo(){}},matchMedia:()=>({matches:true}),
 navigator:{mediaDevices:{async getUserMedia(){events.push('microphone-request');throw Error('Synthetic refusal; no microphone is opened')}}},
 fetch:async(path,opts={})=>{
  calls.push({path,opts});
  if(path==='/api/status')return{ok:true,json:async()=>structuredClone(state)};
  if(path==='/api/pronunciation'){
   const request=JSON.parse(opts.body);
   const value=nextNative?await nextNative:{url:'/out/synthetic-pronunciation.wav',voice:state.pronunciation[request.lang].voice,locale:state.pronunciation[request.lang].locale,kind:'pronunciation-example'};
   return{ok:true,json:async()=>structuredClone(value)};
  }
  throw Error(`Unexpected synthetic request: ${path}`);
 }
});
const run=code=>vm.runInContext(code,context);
const handle=(action,dataset={})=>run(`handle(${JSON.stringify(action)},{dataset:${JSON.stringify(dataset)},disabled:false})`);
vm.runInContext(source,context);
await new Promise(resolve=>setImmediate(resolve));
const main=()=>elements.get('#main').innerHTML;
const nativeCalls=()=>calls.filter(c=>c.path==='/api/pronunciation');
const profileBefore=run('JSON.stringify({config:S.config,mine:S.mine,effective:S.effectiveReferences})');

// Opening and changing languages do not generate examples or play sound.
assert.equal(nativeCalls().length,0);assert.equal(events.filter(e=>e==='native-play').length,0);
assert(main().includes('FULL ING-glish PASS-ij.'));
await handle('record-tab',{code:'ar'});await handle('record-again');
assert(main().includes('Naṣṣ kāmil.'));
assert.equal(nativeCalls().length,0);

// Only the guide matching the exact current passage is rendered. Input edits
// replace that region without rendering the guide for the previous passage.
const recordPart=elements.get('.pronunciation[data-pronunciation-context=record]')||node();
elements.set('.pronunciation[data-pronunciation-context=record]',recordPart);
listeners.input({target:{id:'record-script',value:'كلمات جديدة.'}});
assert(!recordPart.outerHTML.includes('Naṣṣ kāmil.'));
assert(recordPart.outerHTML.includes('no matching Latin-letter guide'));
assert.equal(nativeCalls().length,0);
await handle('native-example',{context:'record'});
assert.deepEqual(JSON.parse(nativeCalls().at(-1).opts.body),{lang:'ar',text:'كلمات جديدة.'});
assert.equal(nativeCalls().at(-1).opts.method,'POST');
assert.equal(events.filter(e=>e==='native-play').length,1);
assert.equal(run('nativeExamples.ar.text'),'كلمات جديدة.');
await handle('native-example',{context:'record'});
assert.equal(nativeCalls().length,1);assert.equal(events.filter(e=>e==='native-play').length,2);

// A cached clip from the old voice cannot be replayed after a capability change.
state.pronunciation.ar.voice='Replacement Arabic';
run('S.pronunciation.ar.voice="Replacement Arabic";render()');
assert(!main().includes('Replay language example'));
await handle('native-example',{context:'record'});
assert.equal(nativeCalls().length,2);
assert.equal(run('nativeExamples.ar.voice'),'Replacement Arabic');

// The audition context requests its own exact passage, not the recording
// prompt, cached guide or any Latin-letter helper.
run('recordMode=false;go(5);auditionLang="en";render()');
assert(main().includes('ING-glish aw-DISH-un.'));
const auditionPart=node();elements.set('.pronunciation[data-pronunciation-context=audition]',auditionPart);
listeners.input({target:{id:'audition-script',value:'A different exact audition.'}});
assert(!auditionPart.outerHTML.includes('ING-glish aw-DISH-un.'));
await handle('native-example',{context:'audition'});
assert.deepEqual(JSON.parse(nativeCalls().at(-1).opts.body),{lang:'en',text:'A different exact audition.'});
assert.equal(run('JSON.stringify({config:S.config,mine:S.mine,effective:S.effectiveReferences})'),profileBefore);
assert.deepEqual(Object.keys(run('auditions')),[]);

// Pending takes and a live recording refuse pronunciation requests entirely.
let count=nativeCalls().length;
run('recorder={state:"recording"}');await handle('native-example',{context:'record'});
run('recorder=null;pending={lang:"ar",url:"blob:fixture",text:"fixture",seconds:1}');await handle('native-example',{context:'record'});
assert.equal(nativeCalls().length,count);
run('pending=null;go(4);recordLang="ar";recordMode=true;render()');

// Both types of in-flight guide protect navigation, language tabs, a new take
// and microphone acquisition. No real recording is attempted.
for(const name of ['guideBusy','nativeBusy']){
 run(`${name}=true;recordMode=false`);
 const step=run('step'),lang=run('recordLang'),beforeMic=events.filter(e=>e==='microphone-request').length;
 run('go(1)');await handle('record-tab',{code:'en'});await handle('record-again');await run('startRecording()');
 assert.equal(run('step'),step);assert.equal(run('recordLang'),lang);assert.equal(run('recordMode'),false);
 assert.equal(events.filter(e=>e==='microphone-request').length,beforeMic);
 run(`${name}=false`);
}

// Exercise a genuinely unresolved synthetic request, rather than just setting
// a busy flag. Its completion cannot change the chosen language or profile.
let resolveNative;
nextNative=new Promise(resolve=>{resolveNative=resolve});
run('recordDrafts.ar="انتظار جديد."');
const pendingRequest=handle('native-example',{context:'record'});
await new Promise(resolve=>setImmediate(resolve));
assert.equal(run('nativeBusy'),true);
await handle('record-tab',{code:'en'});run('go(1)');
assert.equal(run('recordLang'),'ar');assert.equal(run('step'),4);
resolveNative({url:'/out/later-pronunciation.wav',kind:'pronunciation-example'});
await pendingRequest;nextNative=null;
assert.equal(run('nativeBusy'),false);
assert.equal(run('JSON.stringify({config:S.config,mine:S.mine,effective:S.effectiveReferences})'),profileBefore);

// Recording explicitly stops every existing audio element before asking for
// the microphone. The synthetic getUserMedia rejects; no device is opened.
audio.push({pause(){events.push('first-audio-pause')}},{pause(){events.push('second-audio-pause')}});
if(!elements.has('#record-script'))elements.set('#record-script',node());
elements.get('#record-script').value='A bounded synthetic passage.';
events.length=0;
await run('startRecording()');
assert.deepEqual(events.slice(0,3),['first-audio-pause','second-audio-pause','microphone-request']);
assert.equal(run('recorder'),null);
assert.equal(calls.filter(c=>c.path==='/api/accept'||c.path==='/api/finish'||c.path==='/api/setup'||c.path==='/api/reference-choice'||c.path.startsWith('/api/reference?')).length,0);
assert.equal(run('JSON.stringify({config:S.config,mine:S.mine,effective:S.effectiveReferences})'),profileBefore);
console.log('Actual client pronunciation flow passes: matched Latin guides, stale-edit hiding, explicit exact-language/text examples, cached replay, audition context, busy/take/record guards, pause-before-microphone, and no profile/reference/approval writes. Synthetic DOM only; no real microphone, playback, inference or server request.');
