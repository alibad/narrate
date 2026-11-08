import assert from 'node:assert/strict';import {readFile,access,readdir} from 'node:fs/promises';import {execFileSync} from 'node:child_process';import path from 'node:path';import {fileURLToPath} from 'node:url';import {recommend} from '../site/model-policy.js';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');execFileSync(process.execPath,['skill/narrate-video/tests/test_reference_ui.mjs'],{cwd:root,stdio:'inherit'});const read=p=>readFile(path.join(root,p),'utf8');const films=JSON.parse(await read('content/gallery.json'));const catalog=JSON.parse(await read('site/catalog.json'));
assert.deepEqual(films.map(f=>f.id),['en','zh','hi','es','ar','fr','bn','pt','id','ur']);assert.equal(catalog.languages.length,32);
assert.equal(recommend(catalog,['en','ar']).best.id,'chatterbox');assert.equal(recommend(catalog,['en','ar'],'omnivoice').best.id,'omnivoice');assert.equal(recommend(catalog,['en','ar'],'omnivoice','compact').best.id,'chatterbox');assert.equal(recommend(catalog,['afb']).best.id,'omnivoice');assert.equal(recommend(catalog,[]).best,null);assert.throws(()=>recommend(catalog,['invented']));assert.equal(recommend(catalog,['en','ar']).models.find(m=>m.id==='qwen3-base').eligible,false);
const html=await read('site/index.html');assert(!/href=["']#["']/.test(html));assert(!/<\/\w+\s+[^>]+>/.test(html),'Closing tags must not have attributes');assert(html.includes('<option value="omnivoice">'),'OmniVoice must be a real selectable option');for(const match of html.matchAll(/href="#([^"]+)"/g))assert(html.includes(`id="${match[1]}"`),match[1]);
for(const name of ['index.html','guide.html','app.js','model-policy.js','style.css','catalog.json','gallery.json','robots.txt','sitemap.xml','manifest.webmanifest','downloads/narrate-video.zip','assets/brand/mark.svg','assets/brand/apple-icon.png','assets/brand/social.png','assets/studio-language-step.jpg','assets/studio-record-step.jpg','studio-guide.json','media/studio.mp4','media/studio.vtt','assets/brand/favicon.svg'])await access(path.join(root,'dist',name));
for(const f of films){assert(f.video&&f.vtt&&f.poster&&f.duration>15);assert.equal(f.review,'pending');for(const key of ['video','vtt','poster'])await access(path.join(root,'dist',f[key]));const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-of','json',path.join(root,'dist',f.video)],{encoding:'utf8'}));assert(probe.streams.some(s=>s.codec_name==='h264'&&s.width===1920&&s.height===1080&&s.pix_fmt==='yuv420p'));assert(probe.streams.some(s=>s.codec_name==='aac'&&s.sample_rate==='48000'));const vtt=await read('dist'+f.vtt);assert(vtt.startsWith('WEBVTT'));assert.equal((vtt.match(/-->/g)||[]).length,3);}
try{const w=await readdir(path.join(root,'.github/workflows'));assert.equal(w.length,0,'Hosted workflows are not authorized')}catch(e){if(e.code!=='ENOENT')throw e}
console.log('Website checks passed: selection policy, real navigation, ten playable H.264/AAC films, captions, assets and no hosted workflows.');

// A crawler receives the same discoverable collection as a JavaScript browser.
const builtHome=await read('dist/index.html');
assert(builtHome.includes('href="https://www.humanquest.net/"'));
assert(builtHome.includes('href="https://www.humanquest.net/ai-patterns"'));
for(const id of [...films.map(f=>f.id),'studio']){
 assert(builtHome.includes(`/films/${id}/`),`Missing crawlable film link ${id}`);
 const watch=await read(`dist/films/${id}/index.html`);
 assert(watch.includes('<video controls'));
 assert(watch.includes('Human Quest'));
 if(process.env.PUBLIC_SITE_URL){
  assert(watch.includes('"@type":"VideoObject"'));
  assert(watch.includes(`rel="canonical" href="${process.env.PUBLIC_SITE_URL}/films/${id}/"`));
 }
}
console.log('Crawlable film links, watch pages, video metadata and Human Quest footer links verified.');
