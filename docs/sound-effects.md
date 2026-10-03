# Victory and trip cues

The first-place podium cue now uses a short major fanfare, a lower chord, light drum pulses, and sparkling high notes. Second place has a shorter rising phrase. Existing fireworks remain synchronized with the finish animation.

Trips play a descending whistle, soft impact, and two rubbery rebounds when the racer visibly trips, after the camera and action announcement. Reconnect snapshots do not replay the cue.

The cues use Web Audio oscillators and envelopes, require no sound downloads, and work with classic artwork or the optional festival pack. They reuse the existing audio context and SFX output. Voices disconnect after finishing. `audioEffects.ts` accepts a `BaseAudioContext` so the same synthesis can be checked with `OfflineAudioContext`.

Validation includes the trip playback/reconnect regression and offline renders of first place, second place, and trip cues: finite samples, audible RMS, peaks below clipping, and silence at the end of each buffer.
