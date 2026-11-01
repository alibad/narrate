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
the post-action result in its action function. Action annotations are opt-in.
The capture receipt records readiness and dimensions; geometry and playback
review remain pending. No silent rehearsal or replay occurs.
Before the action, the adapter checks the first screencast JPEG and reported
viewport dimensions against the requested viewport. Mismatch or no frame aborts
the take before the action. It also checks subsequent frames. Matching dimensions
still need the four-edge fixture review: padding can conceal missing content.

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

For cards, author local HTML or a diagram, open it in a separate page and capture
a stable screenshot. Include an editorial label and use local fonts/assets.
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
