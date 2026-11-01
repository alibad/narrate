/** Optional browser integration test. Only a new local fixture is manipulated. */
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadBrowser, ready, take } from '../scripts/capture.mjs';

const [entry,executable,mode]=process.argv.slice(2);
const directory=await mkdtemp(join(tmpdir(),'video-capture-test-'));
const browser=await loadBrowser(entry,executable);
try {
  const ctx=await browser.newContext({viewport:{width:640,height:480},deviceScaleFactor:1,reducedMotion:'reduce'});
  const page=await ctx.newPage();
  await page.setContent('<style>body{margin:0;background:#142d44;color:white;border:12px solid #23cd91;box-sizing:border-box;height:100vh;font:24px system-ui}</style><h1>Fixture</h1><button onclick="window.actions=(window.actions||0)+1;document.querySelector(\'#result\').textContent=\'Completed\'">Run</button><p id="result">Ready</p>');
  await assert.rejects(()=>ready(page,{selectors:['#missing'],timeout:500}),/absent/);
  await page.evaluate(()=>{window.ticker=setInterval(()=>document.querySelector('#result').textContent=String(Date.now()),20)});
  await assert.rejects(()=>ready(page,{selectors:['#result'],timeout:700}),/timed out/);
  await page.evaluate(()=>{clearInterval(window.ticker);document.querySelector('#result').textContent='Ready'});
  const opts={selectors:['h1','button','#result'],action:async p=>{
    await p.locator('button').click();assert.equal(await p.locator('#result').innerText(),'Completed');
  }};
  if(mode==='expect-geometry-failure'){
    await assert.rejects(()=>take(page,join(directory,'take'),opts),/geometry mismatch/);
    assert.equal(await page.evaluate(()=>window.actions||0),0,'Geometry must fail before an action');
  } else {
    const result=await take(page,join(directory,'take'),opts);
    assert.equal(result.actionCount,1);assert.equal(await page.evaluate(()=>window.actions),1);
    assert.equal(result.frameGeometry.height,480);assert.equal(result.frameGeometry.width,640);
    await assert.rejects(()=>take(page,join(directory,'take'),opts),/exists/);
  }
  await ctx.close();console.log('Browser fixture checks passed; product behavior remains untested.');
} finally {await browser.close();await rm(directory,{recursive:true,force:true});}
