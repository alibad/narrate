/** Helper checks always; the browser integration test only with a Playwright entry. Only a new local fixture is manipulated. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { access, mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadBrowser, ready, take, card, frameBox, frameSlots, concatList, encodeFrames, frameWriter, fitWindow } from '../scripts/capture.mjs';

// A camera key frames its box at about 60% of the picture, capped, overridable, and stays inside the picture.
assert.deepEqual(frameBox({ x: 600, y: 300, width: 400, height: 100 }, 1600, 900), { cx: .5, cy: .3889, z: 1.8 });
assert.equal(frameBox({ x: 0, y: 0, width: 1200, height: 800 }, 1600, 900).z, 1);
assert.equal(frameBox({ x: 0, y: 0, width: 10, height: 10 }, 1600, 900, { zoom: 1.25 }).z, 1.25);
assert.deepEqual(frameBox({ x: -200, y: 850, width: 100, height: 100 }, 1600, 900, { maxZoom: 2 }), { cx: 0, cy: 1, z: 2 });
assert.throws(() => frameBox({ x: 0, y: 0, width: 10, height: 10 }, 1600, 900, { zoom: 4 }), /1 to 3/);
// Frames that arrive faster than the frame rate replace the slot's picture instead of each taking a whole frame.
const slot = frameSlots(30), arrivals = [0, .01, .02, .034, .05, .2, .2001];
assert.deepEqual(arrivals.map(slot), ['new', 'replace', 'replace', 'new', 'replace', 'new', 'replace']);
// Each kept frame holds until the next; the last holds to the end of the take, so the clip keeps real time.
const listing = concatList([{ file: 'frames/a.jpg', t: 0 }, { file: 'frames/b.jpg', t: .5 }], 2, 30);
assert.deepEqual(listing.trim().split('\n'), ['ffconcat version 1.0', "file 'frames/a.jpg'", 'option framerate 30', 'duration 0.500000',
  "file 'frames/b.jpg'", 'option framerate 30', 'duration 1.500000', "file 'frames/b.jpg'", 'option framerate 30']);
// Every kept frame comes out as its own picture, in order: read at FFmpeg's default 25 fps, four frames 1/60 s apart
// came out green, green, yellow, yellow.
const encoded = await mkdtemp(join(tmpdir(), 'video-capture-encode-'));
try {
  const colours = { red: [255, 0, 0], green: [0, 255, 0], blue: [0, 0, 255], yellow: [255, 255, 0] };
  for (const [fps, times] of [[60, [0, 1 / 60, 2 / 60, 3 / 60]], [30, [0, .034, .07, .1]]]) {
    const clip = join(encoded, String(fps));
    await mkdir(join(clip, 'frames'), { recursive: true });
    const kept = Object.keys(colours).map((name, i) => ({ file: `frames/${name}.jpg`, t: times[i] }));
    for (const f of kept) execFileSync('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', `color=c=${f.file.slice(7, -4)}:s=64x48`, '-frames:v', '1', join(clip, f.file)]);
    await encodeFrames(clip, kept, times[3] + 1 / fps, fps);
    const pixels = execFileSync('ffmpeg', ['-v', 'error', '-i', join(clip, 'action.mp4'), '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']);
    const nearest = p => Object.entries(colours).sort(([, a], [, b]) => a.reduce((s, v, k) => s + Math.abs(v - p[k]), 0) - b.reduce((s, v, k) => s + Math.abs(v - p[k]), 0))[0][0];
    const seen = Array.from({ length: pixels.length / 3 }, (_, i) => nearest(pixels.subarray(3 * i, 3 * i + 3)));
    assert.deepEqual(seen, Object.keys(colours), `${fps} fps frames came out as ${seen}`);
  }
  // A failed frame write is kept and thrown where take() can clean up, not left to end Node as an unhandled rejection.
  const writer = frameWriter();
  writer.write(join(encoded, 'missing', 'f0.jpg'), Buffer.from('x'));
  writer.write(join(encoded, 'after.jpg'), Buffer.from('x'));
  await new Promise(done => setTimeout(done, 50));
  await assert.rejects(() => writer.flush(), /ENOENT/);
  assert.throws(() => writer.check(), /ENOENT/);
  await assert.rejects(() => access(join(encoded, 'after.jpg')), /ENOENT/, 'writes after a failure are skipped');
} finally { await rm(encoded, { recursive: true, force: true }); }
// A window whose toolbar takes 87 rows from the page (full Chrome headless) is grown until the page is the size
// asked for; a window that will not grow fails instead of filming a shorter page.
function windowWithToolbar(rows, grows = true) {
  let bounds = { width: 640, height: 480 };
  const session = { detach: async () => {}, send: async (method, params) => {
    if (method === 'Browser.getWindowForTarget') return { windowId: 1, bounds };
    if (method === 'Browser.getWindowBounds') return { bounds };
    if (method === 'Browser.setWindowBounds' && grows) bounds = { ...bounds, ...params.bounds };
    return {};
  } };
  return { evaluate: async () => ({ width: bounds.width, height: bounds.height - rows }), waitForFunction: async () => {},
           context: () => ({ newCDPSession: async () => session }) };
}
assert.deepEqual(await fitWindow(windowWithToolbar(87), { width: 640, height: 480 }), { width: 640, height: 480 });
await assert.rejects(() => fitWindow(windowWithToolbar(87, false), { width: 640, height: 480 }), /640x393 CSS px, not 640x480/);

const [entry,executable,mode]=process.argv.slice(2);
if (!entry) {
  console.log('Capture helper checks passed; browser fixture skipped (pass a Playwright module entry to run it).');
  process.exit(0);
}
const directory=await mkdtemp(join(tmpdir(),'video-capture-test-'));
const browser=await loadBrowser(entry,executable);
try {
  const ctx=await browser.newContext({viewport:{width:640,height:480},deviceScaleFactor:1,reducedMotion:'reduce'});
  const page=await ctx.newPage();
  const fixture='<style>body{margin:0;background:#142d44;color:white;border:12px solid #23cd91;box-sizing:border-box;height:100vh;font:24px system-ui}</style><h1>Fixture</h1><button onclick="window.actions=(window.actions||0)+1;document.querySelector(\'#result\').textContent=\'Completed\'">Run</button><p id="result">Ready</p>';
  await page.setContent(fixture);
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
    assert.equal(result.clip,'action.webm');
    await assert.rejects(()=>take(page,join(directory,'take'),opts),/exists/);
    const away=await take(page,join(directory,'navigate'),{selectors:['h1','button'],afterSelectors:['#done'],action:async p=>{
      await p.evaluate(()=>{document.body.innerHTML='<h2 id="done">Signed up</h2>'});
    }});
    assert.equal(away.actionCount,1,'targets that the action removes are not checked again');

    // An emulated deviceScaleFactor still screencasts at 1x: sharp capture says so before the action runs.
    const emulated=await browser.newContext({viewport:{width:640,height:480},deviceScaleFactor:1.5,reducedMotion:'reduce'});
    const emulatedPage=await emulated.newPage();
    await emulatedPage.setContent(fixture);
    await assert.rejects(()=>take(emulatedPage,join(directory,'emulated'),{...opts,sharp:true}),/force-device-scale-factor/);
    assert.equal(await emulatedPage.evaluate(()=>window.actions||0),0,'Sharp geometry must fail before an action');
    await emulated.close();

    // Sharp: a browser scaled 1.5x films 960x720 device pixels into a constant-rate H.264 clip, with studio marks.
    const scaled=await loadBrowser(entry,executable,{args:['--force-device-scale-factor=1.5','--window-size=640,480']});
    const sharpCtx=await scaled.newContext({viewport:null,reducedMotion:'reduce'});
    const sharpPage=await sharpCtx.newPage();
    await sharpPage.setContent(fixture.replace('<button ','<button id="run" ')+'<button id="late" disabled>Later</button>');
    let kept;
    const sharp=await take(sharpPage,join(directory,'sharp'),{selectors:['h1','#run','#result','#late'],sharp:true,viewport:{width:640,height:480},holdAfter:900,action:async(p,studio)=>{
      kept=studio;
      await studio.focus(p.locator('#run'));
      await studio.click(p.locator('#run'));
      await p.waitForTimeout(300);
      // A button that only takes a click 0.6 s from now: its sound is marked when the click lands.
      await p.evaluate(()=>setTimeout(()=>{document.querySelector('#late').disabled=false},600));
      studio.wide();
      await studio.click(p.locator('#late'));
    }});
    assert.equal(sharp.clip,'action.mp4');
    assert.deepEqual([sharp.frameGeometry.width,sharp.frameGeometry.height,sharp.sharp.width,sharp.sharp.height],[960,720,960,720]);
    assert.equal(sharp.camera.length,2);assert.ok(sharp.camera[0].z>1&&sharp.camera[1].z===1);
    assert.ok(sharp.camera[0].t<=sharp.sounds[0].at&&sharp.sounds[0].at<sharp.camera[1].t);
    assert.deepEqual(sharp.sounds.map(s=>s.effect),['click','click']);
    assert.ok(sharp.sounds[1].at-sharp.camera[1].t>=.55,`late click marked ${sharp.sounds[1].at-sharp.camera[1].t}s after it was asked for`);
    kept.wide();
    assert.equal(sharp.camera.length,2,'marks after the take ends are ignored');
    const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',join(directory,'sharp','action.mp4')]));
    const video=probe.streams.find(s=>s.codec_type==='video');
    assert.deepEqual([video.width,video.height,video.codec_name,video.r_frame_rate],[960,720,'h264','30/1']);
    // The clip lasts as long as the take was filmed: held frames are not lost and fast frames are not stretched.
    assert.ok(Math.abs(Number(probe.format.duration)-sharp.sharp.seconds)<.07,`clip ${probe.format.duration}s vs ${sharp.sharp.seconds}s filmed`);
    const saved=JSON.parse(await readFile(join(directory,'sharp','capture.json'),'utf8'));
    assert.deepEqual(saved.camera,sharp.camera);

    // A card replaces the page from about:blank and waits for its fonts.
    await card(sharpPage,'<style>body{margin:0;background:#0a0a0a;color:#fafafa;font:600 48px system-ui}</style><h1 id="card">A card</h1>');
    assert.equal(sharpPage.url(),'about:blank');
    assert.equal(await sharpPage.locator('#card').innerText(),'A card');
    await scaled.close();

    // A window that leaves the page short (here 80 rows, as full Chrome's toolbar takes 87) is fitted before the take,
    // so the footer 64 px above the bottom is filmed where the page puts it, in 960x720 frames. Without the size, the
    // take refuses before the action rather than film whatever the window gives.
    const short=await loadBrowser(entry,executable,{args:['--force-device-scale-factor=1.5','--window-size=640,400']});
    const shortPage=await (await short.newContext({viewport:null,reducedMotion:'reduce'})).newPage();
    await shortPage.setContent(fixture+'<footer id="foot" style="position:fixed;bottom:64px;left:24px">Footer</footer>');
    await assert.rejects(()=>take(shortPage,join(directory,'unsized'),{...opts,sharp:true}),/needs take/);
    assert.equal(await shortPage.evaluate(()=>window.actions||0),0,'An unsized take must fail before the action');
    const fitted=await take(shortPage,join(directory,'fitted'),{...opts,selectors:['h1','button','#result','#foot'],sharp:true,viewport:{width:640,height:480}});
    assert.deepEqual([fitted.viewport.width,fitted.viewport.height,fitted.sharp.width,fitted.sharp.height],[640,480,960,720]);
    assert.deepEqual([fitted.frameGeometry.width,fitted.frameGeometry.height],[960,720]);
    assert.equal(await shortPage.evaluate(()=>Math.round(document.querySelector('#foot').getBoundingClientRect().bottom)),480-64);
    await short.close();
  }
  const motion = await ctx.newPage();
  await motion.setContent('<style>@keyframes tint{to{background:red}}body{animation:tint .1s infinite alternate}</style><button id="stable">Ready</button>');
  await assert.rejects(() => ready(motion, { selectors: ['#stable'], stability: 'layout' }), /requires a reason/);
  const scoped = await ready(motion, { selectors: ['#stable'], stability: 'layout', reason: 'Intentional background animation remains visible.' });
  assert.equal(scoped.stability, 'layout');
  assert.equal(scoped.samples, 3);
  await assert.rejects(() => ready(motion, { selectors: ['#missing'], stability: 'layout', reason: 'Animation' }), /absent/);
  await motion.close();
  await ctx.close();console.log('Browser fixture checks passed; product behavior remains untested.');
} finally {await browser.close();await rm(directory,{recursive:true,force:true});}
