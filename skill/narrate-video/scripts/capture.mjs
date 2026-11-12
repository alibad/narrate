/** Explicit Playwright adapter. No package discovery, installs, auth, or action replay. */
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdir, writeFile, readFile, access, rm } from 'node:fs/promises';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const hash = b => createHash('sha256').update(b).digest('hex');
const round = (v, places) => Number(v.toFixed(places));

/** An editorial camera key that frames box `b` (CSS px in a `width` x `height` viewport): the box fills about 60% of
    the picture, never past `maxZoom`; `zoom` overrides. The centre is a share of the picture, as render.py takes it. */
export function frameBox(b, width, height, { zoom, maxZoom = 1.8 } = {}) {
  const z = zoom ?? Math.max(1, Math.min(maxZoom, .6 * width / Math.max(b.width, 1), .6 * height / Math.max(b.height, 1)));
  if (!(z >= 1 && z <= 3)) throw Error('Camera zoom must be 1 to 3');
  const share = v => round(Math.min(1, Math.max(0, v)), 4);
  return { cx: share((b.x + b.width / 2) / width), cy: share((b.y + b.height / 2) / height), z: round(z, 4) };
}

/** Where each arriving frame goes in a constant-rate clip: a new slot when at least 1/fps has passed since the last
    one began, otherwise it replaces that slot's picture. Frames that arrive faster than the frame rate are dropped,
    not each stretched to a whole frame, which made a film drift seconds late (measured 9 Nov 2026). */
export function frameSlots(fps) {
  let last = -Infinity;
  return t => {
    if (t - last >= 1 / fps - 1e-6) { last = t; return 'new'; }
    return 'replace';
  };
}

/** An ffconcat listing that holds each kept frame until the next one, and the last until `end` (seconds). The
    screencast only sends a frame when the page changes, so a still page is one long hold. Each file is read at the
    clip's own frame rate: at FFmpeg's default 25 fps, frames closer than 1/25 s merged and 4 frames at 60 fps came
    out as 2 pictures. */
export function concatList(kept, end, fps) {
  const lines = ['ffconcat version 1.0'];
  kept.forEach((f, i) => lines.push(`file '${f.file}'`, `option framerate ${fps}`, `duration ${Math.max(.001, (kept[i + 1]?.t ?? end) - f.t).toFixed(6)}`));
  lines.push(`file '${kept.at(-1).file}'`, `option framerate ${fps}`);
  return lines.join('\n') + '\n';
}

/** Encode kept frames (`directory`/frames/*.jpg) to `directory`/action.mp4 at a constant `fps`, `filmed` seconds long. */
export async function encodeFrames(directory, kept, filmed, fps) {
  await writeFile(join(directory, 'frames.ffconcat'), concatList(kept, filmed, fps));
  // The listing repeats its last file (the concat demuxer drops the final duration), so trim to the filmed frames.
  await promisify(execFile)('ffmpeg', ['-v', 'error', '-f', 'concat', '-safe', '0', '-i', join(directory, 'frames.ffconcat'),
    '-vf', `fps=${fps},trim=end_frame=${Math.max(1, Math.round(filmed * fps))},scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-preset', 'medium',
    '-crf', '16', '-an', '-movflags', '+faststart', join(directory, 'action.mp4')], { maxBuffer: 1 << 24 });
}

/** Writes frames in order. A failed write (a full disk) is kept for `check()` and `flush()` to throw, so take() still
    stops the screencast and writes failure.json; left unhandled, the rejection ended Node at once. */
export function frameWriter() {
  let queue = Promise.resolve(), error;
  return {
    write(file, data) { queue = queue.then(() => error ? undefined : writeFile(file, data)).catch(e => { error ??= e; }); },
    check() { if (error) throw error; },
    async flush() { await queue; if (error) throw error; },
  };
}

/** Show a card in place of the page. It starts from about:blank: setContent keeps the current document's
    Content-Security-Policy, and an app's policy blocked a card's font (measured 9 Nov 2026). Then every font face loads. */
export async function card(page, html) {
  if (page.url() !== 'about:blank') await page.goto('about:blank');
  await page.setContent(html, { waitUntil: 'load' });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.fonts].map(f => f.load().catch(() => {})));
  });
}
export function jpegSize(bytes) {
  for (let i = 2; i + 8 < bytes.length;) {
    if (bytes[i] !== 0xff) throw Error('Invalid JPEG marker');
    const marker = bytes[i+1], length = bytes.readUInt16BE(i+2);
    if ([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker))
      return { width: bytes.readUInt16BE(i+7), height: bytes.readUInt16BE(i+5) };
    if (length < 2) break;
    i += 2 + length;
  }
  throw Error('JPEG dimensions unavailable');
}
export async function loadBrowser(entry, executablePath, { args = [] } = {}) {
  if (!entry) throw Error('Supply an installed Playwright module entry explicitly');
  const { chromium } = await import(pathToFileURL(resolve(entry)).href);
  return chromium.launch({ ...(executablePath ? { executablePath } : {}), ...(args.length ? { args } : {}) });
}

/** The page's CSS viewport. A context made with `viewport: null` (sharp capture) has none set, so read the window's. */
export async function viewportOf(page) {
  return page.viewportSize() ?? page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
}

/** Make a `viewport: null` page exactly width x height CSS px. A browser's own toolbar can take rows from the window:
    full Chrome headless gave a 1600x813 page for --window-size=1600,900, the headless shell 1600x900 (measured
    10 Nov 2026). Grows the window by what the page is missing, through CDP, and fails rather than film a smaller page. */
export async function fitWindow(page, { width, height }, tries = 3) {
  const inner = () => page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  let now = await inner();
  if (now.width === width && now.height === height) return now;
  const session = await page.context().newCDPSession(page);
  try {
    const { windowId } = await session.send('Browser.getWindowForTarget');
    for (let i = 0; i < tries && (now.width !== width || now.height !== height); i++) {
      const { bounds } = await session.send('Browser.getWindowBounds', { windowId });
      await session.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal', width: bounds.width + width - now.width, height: bounds.height + height - now.height } });
      await page.waitForFunction(([w, h]) => innerWidth === w && innerHeight === h, [width, height], { timeout: 1000 }).catch(() => {});
      now = await inner();
    }
  } finally { await session.detach().catch(() => {}); }
  if (now.width !== width || now.height !== height) throw Error(`The window gives the page ${now.width}x${now.height} CSS px, not ${width}x${height}`);
  return now;
}

/** Check the whole viewport as well as visible, unique targets. Never equate absent with ready. */
export async function ready(page, { selectors, timeout = 10000, interval = 200, samples = 3, stability = "viewport", reason } = {}) {
  if (!Array.isArray(selectors) || !selectors.length) throw Error('Readiness requires explicit selectors');
  if (!['viewport', 'targets', 'layout'].includes(stability)) throw Error('Unknown stability rule');
  if (stability !== 'viewport' && (typeof reason !== 'string' || !reason.trim())) throw Error('Scoped stability requires a reason for intentional motion');
  const deadline = Date.now() + timeout;
  let previous, consecutive = 0;
  while (Date.now() < deadline) {
    const targets = [];
    for (const selector of selectors) {
      const l = page.locator(selector);
      if (await l.count() !== 1 || !await l.isVisible()) throw Error(`Readiness target absent, hidden or ambiguous: ${selector}`);
      const b = await l.boundingBox();
      const vp = await viewportOf(page);
      if (!b || b.x < 0 || b.y < 0 || b.x + b.width > vp.width + .5 || b.y + b.height > vp.height + .5)
        throw Error(`Readiness target clipped: ${selector}`);
      targets.push({ selector, box: b, text: await l.innerText() });
    }
    const media = await page.evaluate(() => ({
      fonts: document.fonts.status === 'loaded',
      images: [...document.images].every(i => i.complete && i.naturalWidth > 0),
    }));
    const pixels = await page.screenshot({ caret: 'hide', animations: 'allow' });
    const stablePixels = stability === 'targets'
      ? await Promise.all(selectors.map(selector => page.locator(selector).screenshot({ caret: 'hide', animations: 'allow' })))
      : stability === "layout" ? [] : [pixels];
    const identity = hash(Buffer.concat([...stablePixels, Buffer.from(JSON.stringify(targets))]));
    consecutive = media.fonts && media.images ? (identity === previous ? consecutive + 1 : 1) : 0;
    previous = identity;
    if (consecutive >= samples) return { pixels, targets, pixelSha256: hash(pixels), samples, interval, stability, reason: reason ?? null, fontsLoaded: true, imagesDecoded: true };
    await page.waitForTimeout(interval);
  }
  throw Error('Readiness timed out: pixels, text, layout, fonts or images still changing; choose a deliberate rule for intentional motion');
}

/** Draw a fixed emphasis box using the visible viewport coordinates, including iframe locators. */
export async function highlight(page, locator, { color = '#27b7a3' } = {}) {
  if (await locator.count() !== 1 || !await locator.isVisible()) throw Error('Highlight target must be unique and visible');
  const b = await locator.boundingBox(), vp = await viewportOf(page);
  if (!b || b.width <= 0 || b.height <= 0) throw Error('Empty highlight target');
  const clipped = { x: Math.max(0, b.x), y: Math.max(0, b.y),
    right: Math.min(vp.width, b.x + b.width), bottom: Math.min(vp.height, b.y + b.height) };
  if (clipped.right <= clipped.x || clipped.bottom <= clipped.y) throw Error('Highlight outside viewport');
  // The outline takes the video's theme colour when one is passed (themes/<name>.json "highlight").
  await page.evaluate(([b, color]) => {
    document.getElementById('__wv_highlight')?.remove();
    const el = document.createElement('div'); el.id = '__wv_highlight';
    Object.assign(el.style, { position: 'fixed', left: `${b.x}px`, top: `${b.y}px`,
      width: `${b.right-b.x}px`, height: `${b.bottom-b.y}px`, outline: `3px solid ${color}`,
      outlineOffset: '-3px', borderRadius: '8px', pointerEvents: 'none', zIndex: '2147483647' });
    document.documentElement.append(el);
  }, [clipped, color]);
}

export async function unhighlight(page) {
  await page.evaluate(() => document.getElementById('__wv_highlight')?.remove());
}

/** Start the recorder only after preparation and readiness, stopping before further setup.
    `sharp: true` keeps every screencast frame at the page's device pixels and encodes them as a constant-rate
    H.264 clip, action.mp4, instead of Playwright's WebM. Chrome screencasts at CSS pixels unless the browser itself
    is scaled: launch with --force-device-scale-factor=1.5 --window-size=1600,900, use `viewport: null` and give the
    take `viewport: { width: 1600, height: 900 }`, the page size to film; the window is fitted to it first.
    The action gets `(page, studio)`: studio.focus(locator), studio.wide() and studio.click(locator) mark editorial
    camera keys and click sounds for render.py, timed from the clip's first frame. */
export async function take(page, directory, { selectors, afterSelectors, action, holdBefore = 500, holdAfter = 700, annotations = false, label = 'demonstration', build = 'unknown', sharp = false, fps = 30, viewport, readiness = {} }) {
  try { await access(directory); throw Error('Capture output exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  if (![24, 30, 60].includes(fps)) throw Error('fps must be 24, 30 or 60');
  // A page without an emulated viewport is as big as its window lets it be, so the take says what size it films.
  if (page.viewportSize() === null) {
    if (!viewport) throw Error('A page made with viewport: null needs take(..., { viewport: { width, height } }), the CSS size to film');
    await fitWindow(page, viewport);
  } else if (viewport && (viewport.width !== page.viewportSize().width || viewport.height !== page.viewportSize().height)) {
    throw Error(`The take asks for ${viewport.width}x${viewport.height} but the page's viewport is ${page.viewportSize().width}x${page.viewportSize().height}`);
  }
  await mkdir(directory, { recursive: true });
  const initial = await ready(page, { ...readiness, selectors });
  await writeFile(join(directory, 'before.png'), initial.pixels);
  const started = new Date().toISOString(), start = performance.now();
  const vp = await viewportOf(page), dpr = await page.evaluate(() => devicePixelRatio);
  const size = sharp ? { width: Math.round(vp.width * dpr), height: Math.round(vp.height * dpr) } : vp;
  let recording = false, decoration, frameGeometry, geometryError, framesSeen = 0, firstFrameAt, stoppedAt;
  // Every frame and mark is stamped on arrival, on this process's clock. The frame's own timestamp runs on Chrome's
  // clock, which was 1.8 s off the scene timer (measured 9 Nov 2026), so pages appeared before their captions.
  const clock = () => firstFrameAt === undefined || stoppedAt !== undefined ? null : round((performance.now() - firstFrameAt) / 1000, 3);
  const marks = { camera: [], sounds: [] }, kept = [], slot = frameSlots(fps), frames = frameWriter();
  // Marks asked for while nothing is being filmed (before the first frame or after the stop) are ignored.
  const studio = {
    async focus(locator, options = {}) {
      const t = clock();
      if (await locator.count() !== 1 || !await locator.isVisible()) throw Error('Camera target must be unique and visible');
      const b = await locator.boundingBox();
      if (b && t !== null) marks.camera.push({ t, ...frameBox(b, vp.width, vp.height, options) });
    },
    wide() {
      const t = clock();
      if (t !== null) marks.camera.push({ t, cx: .5, cy: .5, z: 1 });
    },
    async click(locator, options = {}) {
      // A trial click waits until the target can take the click (enabled, uncovered, still), so the sound is marked
      // when the click lands, not when it was asked for.
      await locator.click({ ...options, trial: true });
      const t = clock();
      if (t !== null) marks.sounds.push({ at: round(t + .05, 3), effect: 'click' });
      await locator.click(options);
    },
  };
  try {
    if (action) {
      if (!page.screencast?.start) throw Error('Capture needs Playwright >=1.59 with screencast support');
      if (annotations) decoration = await page.screencast.showActions({ cursor: 'pointer', duration: 350, position: 'top-right' });
      if (sharp) await mkdir(join(directory, 'frames'));
      let signal;
      const firstFrame = new Promise(resolve => { signal = resolve; });
      await page.screencast.start({ ...(sharp ? {} : { path: join(directory, 'action.webm') }), size, quality: sharp ? 92 : 95,
        onFrame: frame => {
          if (stoppedAt !== undefined) return;
          const now = performance.now();
          firstFrameAt ??= now;
          framesSeen++;
          try {
            const got = jpegSize(frame.data);
            frameGeometry = { ...got, reportedViewportWidth: frame.viewportWidth, reportedViewportHeight: frame.viewportHeight };
            if (got.width !== size.width || got.height !== size.height || frame.viewportWidth !== vp.width || frame.viewportHeight !== vp.height)
              geometryError = `Recorder geometry mismatch: expected ${size.width}x${size.height}, received JPEG ${got.width}x${got.height}, viewport ${frame.viewportWidth}x${frame.viewportHeight}`
                + (sharp && dpr !== 1 && got.width === vp.width ? '. Chrome screencasts an emulated deviceScaleFactor at 1x: launch with --force-device-scale-factor and --window-size, and make the context with viewport: null' : '');
          } catch (e) { geometryError = String(e); }
          if (sharp) {
            if (slot((now - firstFrameAt) / 1000) === 'new') kept.push({ file: `frames/f${String(kept.length).padStart(6, '0')}.jpg`, t: (now - firstFrameAt) / 1000 });
            frames.write(join(directory, kept.at(-1).file), frame.data);
          }
          signal();
        } });
      recording = true;
      let timer;
      try { await Promise.race([firstFrame,new Promise((_,reject) => { timer=setTimeout(()=>reject(Error('Recorder supplied no initial frame')),5000); })]); }
      finally { clearTimeout(timer); }
      if (geometryError) throw Error(geometryError); // fail before executing the action
      frames.check();
      await page.waitForTimeout(holdBefore);
      await action(page, studio); // exactly once; callers authorize the actual action
      if (decoration) { await page.screencast.hideActions(); decoration = null; }
      const result = await ready(page, { ...readiness, selectors: afterSelectors ?? selectors }); // the action may navigate away from the first targets
      await page.waitForTimeout(holdAfter);
      stoppedAt = performance.now();
      await page.screencast.stop(); recording = false;
      if (geometryError) throw Error(geometryError);
      await writeFile(join(directory, 'after.png'), result.pixels);
      if (sharp) {
        await frames.flush();
        await encodeFrames(directory, kept, (stoppedAt - firstFrameAt) / 1000, fps);
        await rm(join(directory, 'frames'), { recursive: true });
        await rm(join(directory, 'frames.ffconcat'));
      }
    } else await writeFile(join(directory, 'after.png'), initial.pixels);
    const receipt = { version: 1, started, label, build, viewport: vp, devicePixelRatio: dpr,
      durationWallMs: performance.now() - start, startPixelSha256: initial.pixelSha256,
      readiness: { samples: initial.samples, interval: initial.interval, fonts: true, images: true },
      frameGeometry, framesSeen,
      clip: action ? (sharp ? 'action.mp4' : 'action.webm') : null,
      ...(sharp && action ? { sharp: { fps, width: size.width, height: size.height, framesKept: kept.length, seconds: round((stoppedAt - firstFrameAt) / 1000, 3) } } : {}),
      camera: marks.camera, sounds: marks.sounds,
      readiness: { stability: initial.stability, reason: initial.reason },
      actionExecuted: Boolean(action), actionCount: action ? 1 : 0,
      geometryReview: 'pending', playbackReview: 'pending' };
    await writeFile(join(directory, 'capture.json'), JSON.stringify(receipt, null, 2));
    return receipt;
  } catch (e) {
    await frames.flush().catch(() => {});
    await writeFile(join(directory, 'failure.json'), JSON.stringify({error:String(e),frameGeometry,framesSeen,valid:false},null,2));
    throw e;
  } finally {
    stoppedAt ??= performance.now();
    if (recording) await page.screencast.stop().catch(() => {});
    if (decoration) await page.screencast.hideActions().catch(() => {});
  }
}

// CLI runs an agent-authored entry exactly once. No hidden rehearsal.
if (typeof process !== 'undefined' && process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [entry, moduleEntry, browserPath] = process.argv.slice(2);
  if (!entry || !moduleEntry) throw Error('Usage: node capture.mjs scene-entry.mjs playwright-entry.mjs [browser-executable]');
  const scene = await import(pathToFileURL(resolve(entry)).href);
  const browser = await loadBrowser(moduleEntry, browserPath, scene.launch); // an entry may export launch = { args }
  try { await scene.default(browser, { ready, take, highlight, unhighlight, card, fitWindow }); }
  finally { await browser.close(); }
}
