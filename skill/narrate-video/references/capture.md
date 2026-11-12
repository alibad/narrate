# Capture, cards and emphasis

`scripts/capture.mjs` is an optional Playwright adapter. Supply the exact installed
module entry and browser executable; it does not search caches or install them.
Its bounded recorder uses `page.screencast` (Playwright >=1.59). Verify the chosen
runtime API locally. Driver failure is an error, not a hidden switch to another
browser. Close the browser in `finally` and stop each take before more setup.

The agent writes an entry module whose default export takes `(browser, helpers)`.
Create a fresh context with an explicit viewport/DPR/locale and navigate to the
authorized target. Use normal application authentication outside the public
package. The adapter includes no cookie minting, demo login, storage clearing or
product-specific selectors. Do not commit credentials, browser profiles or state.
Use DPR 1 for matching still/clip pixel coordinates; review coordinates separately
when choosing another DPR.

Call `helpers.take(page, NEW_DIRECTORY, {selectors, action, build, label})`.
With no action it saves stable stills; otherwise it records the action exactly
once, using `holdBefore` and `holdAfter` in milliseconds. The caller verifies
the post-action result in its action function. When the action navigates or removes the
first targets, pass `afterSelectors` for the page it leads to; otherwise `selectors` are
checked again after the action. Action annotations are opt-in.
The capture receipt records readiness and dimensions; geometry and playback
review remain pending. No silent rehearsal or replay occurs.
Before the action, the adapter checks the first screencast JPEG and reported
viewport dimensions against the requested viewport. Mismatch or no frame aborts
the take before the action. It also checks subsequent frames. Matching dimensions
still need the four-edge fixture review: padding can conceal missing content.

### Sharp takes and studio marks

`take(..., { sharp: true })` keeps every screencast frame and encodes them as
`action.mp4` (H.264, CRF 16, constant 30 fps; `fps` 24 or 60 also work) instead
of Playwright's WebM. Frames are stamped when they arrive, not with the
frame's own timestamp: Chrome's clock was 1.8 s off the take's (measured 9 Nov
2026). At most one frame is kept per frame interval, the newest winning, and
each holds until the next, so the clip keeps real time.

Chrome screencasts at CSS pixels even when a context emulates a
`deviceScaleFactor` (measured 10 Nov 2026), so for 1.5x pixels scale the
browser itself, with Playwright's headless shell, and leave the viewport to the
window. A scene entry can export its launch arguments:

```js
export const launch = { args: ['--force-device-scale-factor=1.5', '--window-size=1600,900'] };
export default async (browser, { take }) => {
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();
  // ...
  await take(page, dir, { sharp: true, viewport: { width: 1600, height: 900 }, ... }); // 2400x1350 frames
};
```

A `viewport: null` page is as big as its window lets it be: full Chrome headless
keeps a toolbar in the window and gave a 1600x813 page for
`--window-size=1600,900` (measured 10 Nov 2026). So the take states the page
size it films (`viewport`); it grows the window through CDP until the page is
exactly that size, or fails before the action (`fitWindow` does this on its own).
Every frame is then checked against that size. An emulated scale fails the
geometry check before the action, with this hint.

The action receives `(page, studio)`. `studio.focus(locator, { zoom, maxZoom })`
marks an editorial camera key that frames the target (about 60% of the
picture, at most 1.8x), `studio.wide()` returns to the whole picture and
`studio.click(locator)` clicks with a click sound. Marks are timed from the
clip's first frame and saved in `capture.json` as `camera` and `sounds`; copy
them into the plan's clip scene, subtracting `clipStart`. Marks made while
nothing is filmed are ignored. With the default WebM the times are close
but not frame-exact; use `sharp` for camera moves.

`card(page, html)` shows a card from `about:blank`, so the app's
Content-Security-Policy cannot block the card's font, and waits for its fonts.
Use it on its own page or between takes, then `take` it without an action.

`ready` requires unique, visible, unclipped target selectors, loaded fonts and
images, and three identical viewport PNG/target snapshots separated by 200 ms.
Prepare scrolling first. A missing selector fails immediately. Intentional
animation, video, blinking text and canvases can prevent readiness: choose a
documented target-specific rule or an external recorder, rather than weakening
the gate globally. A stable screen can still be wrong; verify its content.
CSS images, cross-origin frames and background polling need target-specific
review. Preserve meaningful animations when they are what the video explains.

`highlight(page, locator)` draws a fixed viewport-clipped outline and supports
an iframe locator through its page-coordinate bounding box. It is emphasis,
not proof of a click. Scrollable ancestor clipping and transformed frames need
inspection; use a narrowly visible target. `unhighlight` removes the outline.

For cards, author local HTML or a diagram and capture a stable screenshot at the
film's frame size (1920×1080 for a landscape film). Use a separate headless
browser with a fresh profile, never the user's browser, for example:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --user-data-dir="$(mktemp -d)" --window-size=1920,1080 --force-device-scale-factor=1 \
  --screenshot="$PWD/captures/intro.png" "file://$PWD/cards/intro.html"
```

Capture twice and compare the files to confirm the card is stable, or use
`helpers.take` without an action. Use local fonts and assets. The renderer's
header already shows each scene's status; keep an editorial label on the card
itself when the film hides the header (`header: false`).
Do not replace the active application with a card mid-take. A minimal neutral
card example is in `examples/card.html`; it has no animation or remote resources.

Before a new browser/driver combination, record a fixture with all four marked
edges and compare the encoded result to its screenshot, including the bottom.
The official [video documentation](https://playwright.dev/docs/videos) describes
viewport/video fitting; explicit dimensions still need an empirical edge check.
See [screencast API](https://playwright.dev/docs/api/class-screencast) for start/stop.
Do not paint over grey strips or infer universal geometry from one browser run.

Investigate flicker with fixed build/state/viewport/DPR, one variable at a time:
static hold; navigation; card replacement; animated card; overlay insertion;
font/image readiness. Compare adjacent decoded frames inside expected holds,
separately from intentional cuts. Preserve raw video and a timestamped anomaly
log. A controlled fixture can reproduce a mechanism but cannot establish the
cause of an unavailable historical product recording.

For an intentionally animated screen, pass `readiness: { stability: "targets",
reason: "Describe the animation that must remain visible" }` to `take`. This
compares repeated pixels, text and geometry of the explicit target controls
instead of the whole viewport. Full frames are retained, and the receipt records
the narrower rule and reason. Missing, clipped or unstable targets still fail.
Do not use this to bypass unresolved loading or flicker.

When intentional effects also animate behind the controls, `stability: "layout"`
requires the same explicit reason and checks repeated target text/geometry and
loaded fonts/images without claiming pixel stability. Preserve full frames for
visual review. Use it only for intentional motion, never unresolved loading.

For a canvas-rendered application such as Flutter, use its accessibility controls
and verify the application accepted typed text. Semantic input proxies can show
a DOM value before the application controller commits it; use real keyboard
entry with settled field focus rather than treating a successful fill as proof.
Keep authentication setup and credentials outside recorded takes.
