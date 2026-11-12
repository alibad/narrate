# Agent-authored edit plan

Install no services to render. Python needs Pillow; FFmpeg/ffprobe must be on
PATH. Work inside an isolated production folder; all media paths are relative
to its plan file and must resolve inside that folder.

```json
{
  "version": 1, "width": 1080, "height": 1920, "fps": 30,
  "voice": {"provider": "supplied-recording", "model": "human", "revision": "take-1", "name": "authorized narrator", "language": "en"},
  "scenes": [{
    "kind": "still", "status": "demonstration", "title": "Choose a voice",
    "visual": "captures/choice.png", "audio": "speech/choice.wav",
    "say": "Choose the voice for this video.",
    "captions": [{"start": 0, "end": 2.2, "text": "Choose the voice for this video."}]
  }]
}
```

This example documents the schema; its asset paths are illustrative. Use the
voice identity that actually produced the files. The renderer preserves that
declaration; it cannot independently verify a provider or the spoken content.

- `kind`: `still` or `clip`; `status`: `observed`, `demonstration`, `editorial`.
  This status remains visible above the media. Use demonstration for synthetic
  screens/data, even when the clicks and resulting UI behavior are real.
- Observed scenes need `evidence` strings `capturedAt`, `surface`, `target`,
  `action`, `build`. Use `unknown` for an uncorroborated served build. A local
  commit alone does not prove which code a server served. Hashes identify files,
  not the truth of the visible content.
- `clipStart`, `clipEnd`: source trim in seconds; clipStart defaults to 0.
  The action retains its original speed, source audio is discarded, and its
  last frame holds if speech continues. Do not stretch a still to imply action.
- Optional `crop`: `[left, top, right, bottom]` in source pixels. This is a
  deliberate editorial crop with the original retained. Inspect context before
  using it for a product claim. No cropping happens implicitly.
- `audio` and nonempty `say` are required for final output. The scene lasts
  at least audio duration + .35 seconds, the selected clip span and optional
  `minDuration`. Maximum: 40 scenes, 90 seconds per scene.
- Captions: explicit ordered, nonoverlapping `start`, `end`, `text` relative to
  the scene; maximum two rendered lines. Invalid/too-short intervals, text
  overflow and silent audio stop rendering. Both burned captions and SRT use
  the same boundaries rounded to output frames. No silent truncation.
- Dimensions: even, 360–3840; aspect .5–2; fps 24, 30 or 60. Portrait needs a
  separately chosen viewport/crop. It is not a resized landscape composition.
- `captionSize`: optional integer size in pixels, at least 16 and no greater than
  six percent of frame height. Use only after inspecting the actual caption
  rendering; overflow still fails. CJK text wraps without requiring spaces.
- `font`: optional relative font file. Pillow's built-in default covers plain
  English only: it has no é, ñ, ü, en or em dash, or €. The renderer checks
  every caption and title character against the font in use and names any
  missing glyph, so supply an appropriately licensed font for accented Latin
  and non-Latin text and inspect shaping. Fonts are not bundled; like every
  asset, the file must sit inside the production folder, so copy in one you
  may use, such as Inter (SIL Open Font License). Arabic also
  needs Pillow with RAQM (`PIL.features.check("raqm")`); on Windows that needs
  the FriBiDi DLL on `PATH`, which Pillow's wheels do not include.

### Optional look for a finished film

All are off by default; the default output is unchanged.

- `background`: `"#rrggbb"` frame colour around the visual, header and
  captions. Match it to the material, for example dark chart backgrounds.
- `header`: `false` hides the status and title band and gives its height to the
  visual. The status still goes into `evidence.json`; say elsewhere (credits,
  description) which parts are editorial or demonstration material.
- `stillMotion`: `"push"` gives every still a slow 5% push-in. A scene's own
  `motion` (`"push"` or `"none"`) overrides it. This is an editorial camera
  move: a clip keeps its own movement, and a moving still must not be used to
  imply product behaviour.
- `transition`: `{"type": "crossfade", "seconds": 0.4}` (0.1 to 1, at most half
  the shortest scene). Each scene still starts on its planned frame and fades
  in over the previous scene's held last frame, so captions, the SRT and the
  total length do not move. Only the picture fades: the header and caption
  bands switch on the scene's first frame, so a new caption is at full strength
  when its SRT cue starts. The first `seconds` of each scene's picture are
  blended; start an action clip after that.

### Studio finish

Also off by default. Use them for a finished, product-film cut; none changes
action speed, scene timing or the SRT.

- `camera` on a clip scene: editorial camera keys, `[{"t": 1.2, "cx": .3,
  "cy": .4, "z": 1.6}]`. `t` is scene seconds within the clip (ascending),
  `cx`/`cy` the centre as a share of the picture, `z` 1 (whole picture) to 3.
  Each move eases over 0.9 s; one asked for before the last has landed waits
  for it. Moves, like `push`, are drawn to a fraction of a pixel, so text
  glides instead of shimmering. The zoom is made on the source pixels, so pair it with a sharp
  capture ([capture](capture.md)), which also writes these keys. The receipt
  records `motion: "camera"` and the keys. Like `push`, it is an editorial
  camera move: it must not suggest behaviour the product did not show. The keys
  frame the whole capture, so a clip with `camera` cannot also have a `crop`:
  frame the detail with the camera instead.
- `captionStyle`: `"lowerThird"` draws each caption as a card over the bottom
  of the picture (Narrate paper and ink colours with a coral accent) instead of a band below it. The picture
  takes the band's height. Cards are laid over the finished picture, so they
  never zoom, and they cut on the SRT's frames, also inside a crossfade. They
  cover part of the picture: keep the evidence clear of the bottom-left.
- `music`: `{"level": 0.3}` (0.05 to 1) lays a generated bed
  (`scripts/soundbed.py`) under the film, ducked while the narrator speaks.
- `sounds` on a scene: `[{"at": 0.8, "effect": "click"}]`, scene seconds;
  effects are `click` and `whoosh`, generated when the film is rendered
  (`scripts/sfx.py`). A whoosh suits a card's first frame; a capture's `sounds`
  give clicks.
- `fade`: `{"in": 0.5, "out": 0.8}` seconds (up to 3, at most half the first
  or last scene) opens from and closes to the frame colour, picture and sound.
  A caption on those frames fades with them.

A `--silent-preview` has no narration but keeps `music` and `sounds`, so their
timing can be checked before the voice is ready.

No option speeds up or skips footage. To cut a long wait for an answer, end the
clip before it and start a new take on the result.

Header/caption zones sit outside the fitted UI. The renderer encodes once,
normalizes mixed screen captures to limited-range BT.709 H.264/yuv420p,
strips container metadata, normalizes toward -18 LUFS and writes MP4, captions,
script and evidence. Measure the final loudness; a target is not a measurement.
Receipts copy supplied voice/evidence fields; review those strings before sharing.
