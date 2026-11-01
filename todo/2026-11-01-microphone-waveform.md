# Restore the earlier microphone waveform

Restored the earlier rolling bar waveform in place of the instantaneous thin trace. Bars are drawn from actual microphone peak samples at a stable cadence. Playback/new-take previews use normalized audio peaks, adaptive bar counts and device-pixel scaling, with playback progress and Arabic direction support. A stopped take keeps its waveform before saving. Resize/animation listeners are cleaned up on navigation.

The running local studio and portable source were updated. No reference audio, transcript, accepted audition or model was replaced. The downloadable archive and file hashes are rebuilt from the source. The five-step language/model flow is preserved.

Verification: inline JavaScript parses, all 35 skill tests pass in the configured audio Python, and the public build/verification pass. The browser exercised recording, stop and pending-take preview with a clearly labelled synthetic audio fixture; no microphone capture was started. Actual saved-reference rendering was inspected separately. QA fixtures and screenshots remain outside the source package.
