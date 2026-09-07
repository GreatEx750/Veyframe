# Preview playback continuity fix

## Confirmed defect

Normal media `timeupdate` events updated React's `playheadMs`. An effect watching
that same state wrote the rounded time back to `video.currentTime`, triggering
unrequested seeks and interrupting playback. The hosted Spotlight reproduced
28 seeks and 28 waiting events in 10.09 wall-clock seconds; the video advanced
only 6.37 seconds at a reported playback rate of 1. The user confirmed the
downloaded MP4 sounds normal outside the editor.

## Change

- Removed the state-to-media seek effect. Normal playback only reports position.
- Added one explicit seek handler for timeline scrubbing, captions, Sources links,
  Story sections and Quality timestamps. Explicit seeks also update the UI.
- Simplified the selected Sources contribution render expression so event handlers
  remain outside an immediately invoked render closure and satisfy React lint.
- No audio processing, generated media, typography, layout or AI configuration changed.
- Added a web-only Cloud Build configuration, scoped to the explicitly selected project.

## Verification

- New regression tests first failed: each playback update caused a currentTime write.
- Editor tests: 34 passed, including normal playback while playing/paused, deliberate
  seeks while playing/paused, and caption navigation.
- Full web package: 95 passed; repository lint and typecheck passed.
- Production readiness passed (333 files). Full repository run passed: 534 tests
  (405 Python, 95 web, 27 TypeScript contracts, 7 runner); four opt-in provider skips.
- Cloud build: `0762c00d-3a6b-4539-ab35-70c41638d5a6`, succeeded.
- Web revision `demodirector-web-00003-5hg` serves 100% of traffic in
  `demodirector-507722`, us-central1. Only the web service was updated.
- Image digest: `sha256:375e87b7231b56dc0b6c65fc1c77b7b3e962a6f6483f01455af585857681c577`.

### Hosted continuity results

| Saved project | Wall time | Media progress | Unwanted seeks | Waiting events |
| --- | --- | --- | --- | --- |
| Spotlight `208f7496-2c97-4f69-956a-0e00989a7c59` | 10.091s | 9.986s | 0 | 0 |
| Presentation `3f2f0ae4-d63e-44a2-ad0c-4edeb69fa9e9` | 10.088s | 9.979s | 0 | 0 |

Both also passed pause, intentional timeline seek and resume. Each deliberate seek
produced exactly one seek event, with no feedback-loop seeks afterward. Existing
exports were not regenerated or modified by the player fix. Refresh an already-open
editor tab to load the updated web application.

## Resolved check failures

- Initial test added an unsupported Testing Library `exact` option; removed it.
- React lint flagged the nested Sources render closure after explicit seeking was
  introduced; resolved by deriving selected contribution data before rendering.
- Initial build submission used a service account lacking access to the source
  archive. Resubmitted with the existing account used by prior successful builds;
  no IAM permissions or HabiWatch resources changed.

The live regression helper is `scripts/diagnose-preview-playback.py --assert-smooth`.
It requires zero unsolicited seeks, zero waiting events and near-real-time progress,
then checks pause, an intentional timeline seek and resume. It does not claim to
evaluate perceptual TTS quality or word-level subtitle alignment.
