/** Explicit Playwright adapter. No package discovery, installs, auth, or action replay. */
import { createHash } from 'node:crypto';
import { mkdir, writeFile, readFile, access } from 'node:fs/promises';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';

const hash = b => createHash('sha256').update(b).digest('hex');
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
export async function loadBrowser(entry, executablePath) {
  if (!entry) throw Error('Supply an installed Playwright module entry explicitly');
  const { chromium } = await import(pathToFileURL(resolve(entry)).href);
  return chromium.launch(executablePath ? { executablePath } : {});
}

/** Check the whole viewport as well as visible, unique targets. Never equate absent with ready. */
export async function ready(page, { selectors, timeout = 10000, interval = 200, samples = 3 } = {}) {
  if (!Array.isArray(selectors) || !selectors.length) throw Error('Readiness requires explicit selectors');
  const deadline = Date.now() + timeout;
  let previous, consecutive = 0;
  while (Date.now() < deadline) {
    const targets = [];
    for (const selector of selectors) {
      const l = page.locator(selector);
      if (await l.count() !== 1 || !await l.isVisible()) throw Error(`Readiness target absent, hidden or ambiguous: ${selector}`);
      const b = await l.boundingBox();
      const vp = page.viewportSize();
      if (!b || b.x < 0 || b.y < 0 || b.x + b.width > vp.width + .5 || b.y + b.height > vp.height + .5)
        throw Error(`Readiness target clipped: ${selector}`);
      targets.push({ selector, box: b, text: await l.innerText() });
    }
    const media = await page.evaluate(() => ({
      fonts: document.fonts.status === 'loaded',
      images: [...document.images].every(i => i.complete && i.naturalWidth > 0),
    }));
    const pixels = await page.screenshot({ caret: 'hide', animations: 'allow' });
    const identity = hash(Buffer.concat([pixels, Buffer.from(JSON.stringify(targets))]));
    consecutive = media.fonts && media.images ? (identity === previous ? consecutive + 1 : 1) : 0;
    previous = identity;
    if (consecutive >= samples) return { pixels, targets, pixelSha256: hash(pixels), samples, interval, fontsLoaded: true, imagesDecoded: true };
    await page.waitForTimeout(interval);
  }
  throw Error('Readiness timed out: pixels, text, layout, fonts or images still changing; choose a deliberate rule for intentional motion');
}

/** Draw a fixed emphasis box using the visible viewport coordinates, including iframe locators. */
export async function highlight(page, locator) {
  if (await locator.count() !== 1 || !await locator.isVisible()) throw Error('Highlight target must be unique and visible');
  const b = await locator.boundingBox(), vp = page.viewportSize();
  if (!b || b.width <= 0 || b.height <= 0) throw Error('Empty highlight target');
  const clipped = { x: Math.max(0, b.x), y: Math.max(0, b.y),
    right: Math.min(vp.width, b.x + b.width), bottom: Math.min(vp.height, b.y + b.height) };
  if (clipped.right <= clipped.x || clipped.bottom <= clipped.y) throw Error('Highlight outside viewport');
  await page.evaluate(b => {
    document.getElementById('__wv_highlight')?.remove();
    const el = document.createElement('div'); el.id = '__wv_highlight';
    Object.assign(el.style, { position: 'fixed', left: `${b.x}px`, top: `${b.y}px`,
      width: `${b.right-b.x}px`, height: `${b.bottom-b.y}px`, outline: '3px solid #27b7a3',
      outlineOffset: '-3px', borderRadius: '8px', pointerEvents: 'none', zIndex: '2147483647' });
    document.documentElement.append(el);
  }, clipped);
}

export async function unhighlight(page) {
  await page.evaluate(() => document.getElementById('__wv_highlight')?.remove());
}

/** Start the recorder only after preparation and readiness, stopping before further setup. */
export async function take(page, directory, { selectors, action, holdBefore = 500, holdAfter = 700, annotations = false, label = 'demonstration', build = 'unknown' }) {
  try { await access(directory); throw Error('Capture output exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  await mkdir(directory, { recursive: true });
  const initial = await ready(page, { selectors });
  await writeFile(join(directory, 'before.png'), initial.pixels);
  const started = new Date().toISOString(), start = performance.now();
  let recording = false, decoration, frameGeometry, geometryError, framesSeen = 0;
  try {
    if (action) {
      if (!page.screencast?.start) throw Error('Capture needs Playwright >=1.59 with screencast support');
      if (annotations) decoration = await page.screencast.showActions({ cursor: 'pointer', duration: 350, position: 'top-right' });
      let signal;
      const firstFrame = new Promise(resolve => { signal = resolve; });
      await page.screencast.start({ path: join(directory, 'action.webm'), size: page.viewportSize(), quality: 95,
        onFrame: frame => {
          framesSeen++;
          try {
            const size = jpegSize(frame.data), vp = page.viewportSize();
            frameGeometry = { ...size, reportedViewportWidth: frame.viewportWidth, reportedViewportHeight: frame.viewportHeight };
            if (size.width !== vp.width || size.height !== vp.height || frame.viewportWidth !== vp.width || frame.viewportHeight !== vp.height)
              geometryError = `Recorder geometry mismatch: expected ${vp.width}x${vp.height}, received JPEG ${size.width}x${size.height}, viewport ${frame.viewportWidth}x${frame.viewportHeight}`;
          } catch (e) { geometryError = String(e); }
          signal();
        } });
      recording = true;
      let timer;
      try { await Promise.race([firstFrame,new Promise((_,reject) => { timer=setTimeout(()=>reject(Error('Recorder supplied no initial frame')),5000); })]); }
      finally { clearTimeout(timer); }
      if (geometryError) throw Error(geometryError); // fail before executing the action
      await page.waitForTimeout(holdBefore);
      await action(page); // exactly once; callers authorize the actual action
      if (decoration) { await page.screencast.hideActions(); decoration = null; }
      const result = await ready(page, { selectors });
      await page.waitForTimeout(holdAfter);
      await page.screencast.stop(); recording = false;
      if (geometryError) throw Error(geometryError);
      await writeFile(join(directory, 'after.png'), result.pixels);
    } else await writeFile(join(directory, 'after.png'), initial.pixels);
    const receipt = { version: 1, started, label, build, viewport: page.viewportSize(),
      devicePixelRatio: await page.evaluate(() => devicePixelRatio),
      durationWallMs: performance.now() - start, startPixelSha256: initial.pixelSha256,
      readiness: { samples: initial.samples, interval: initial.interval, fonts: true, images: true },
      frameGeometry, framesSeen,
      actionExecuted: Boolean(action), actionCount: action ? 1 : 0,
      geometryReview: 'pending', playbackReview: 'pending' };
    await writeFile(join(directory, 'capture.json'), JSON.stringify(receipt, null, 2));
    return receipt;
  } catch (e) {
    await writeFile(join(directory, 'failure.json'), JSON.stringify({error:String(e),frameGeometry,framesSeen,valid:false},null,2));
    throw e;
  } finally {
    if (recording) await page.screencast.stop().catch(() => {});
    if (decoration) await page.screencast.hideActions().catch(() => {});
  }
}

// CLI runs an agent-authored entry exactly once. No hidden rehearsal.
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [entry, moduleEntry, browserPath] = process.argv.slice(2);
  if (!entry || !moduleEntry) throw Error('Usage: node capture.mjs scene-entry.mjs playwright-entry.mjs [browser-executable]');
  const scene = await import(pathToFileURL(resolve(entry)).href);
  const browser = await loadBrowser(moduleEntry, browserPath);
  try { await scene.default(browser, { ready, take, highlight, unhighlight }); }
  finally { await browser.close(); }
}
