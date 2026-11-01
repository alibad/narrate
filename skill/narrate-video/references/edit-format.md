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
- `font`: optional relative font file; required for non-Latin text. Use an
  appropriately licensed font, inspect glyph coverage, and check RAQM for Arabic.
  Fonts are not bundled. Default Latin text uses Pillow's built-in font.

Header/caption zones sit outside the fitted UI. The renderer encodes once,
strips container metadata, normalizes toward -18 LUFS and writes MP4, captions,
script and evidence. Measure the final loudness; a target is not a measurement.
Receipts copy supplied voice/evidence fields; review those strings before sharing.
