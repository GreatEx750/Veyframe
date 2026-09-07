# Local YouTube upload verification

## Delivered

Added a local-only Upload to YouTube dialog beside Download MP4 for completed, non-stale project exports. Supports Google web-server OAuth, destination-channel confirmation, editable title/description, required audience selection and explicit upload permission, private background transfer in 8 MiB chunks, byte progress, and a validated YouTube video link. The existing export is uploaded without rerendering or starting generation. Existing editor colors and typography were retained using the UI styling guide.

OAuth state is random, expires after ten minutes, is session-bound and single-use. Endpoints require authenticated sessions even in optional-auth development mode; all project/export reads enforce ownership. Mutation requests require the local origin. Remote hosts, arbitrary proxy paths and Cloud Run execution are blocked. Google upload locations are allowlisted; tokens and provider payloads are never returned to the browser. Tokens remain in memory with no offline/refresh-token request; disconnect revokes access. Completed upload job objects release their token reference. One active upload per session and repeated-export deduplication prevent ordinary double-click uploads. Network uncertainty is shown explicitly without automatic retry.

## Verification

- Tests were added before the service implementation and initially failed on the missing module.
- Nine focused Python checks passed, including a simulated HTTP-route flow from OAuth consent through an owned saved export, private upload and returned video ID. Covers state isolation/reuse/expiry/cancellation, schema rejection, ownership, same-origin checks, unknown results, chunk progress, duplicate submission and malicious upload destinations.
- Full API regression: 264 passed, three opt-in provider tests skipped. The additional saved-export route test was added after this suite started and passed in the final nine-test focused run.
- Web package: 126 tests passed, including consent gating, missing credentials, selected export payload, success links and proxy/callback protections.
- Contracts: 27 passed. Runner: seven passed.
- Repository lint and strict typecheck passed (165 Python source/test files). Production web build passed. Readiness scan passed (396 files before this report). Targeted whitespace checks passed.
- Real local browser check on the saved marketing presentation: upload dialog visible, honest missing-credentials instructions, no upload action before setup, mobile dialog width and close behavior passed. Screenshots: `artifacts/youtube-local/desktop.png` and `mobile.png`.
- Browser verification first found an outdated local API process returning 404. Confirmed no active local generation jobs, restarted only the API, then rechecked successfully.

## Not yet verified with Google

No YouTube OAuth client ID or secret exists in the local environment. No real channel was authorized and no video was uploaded to Google. Provider calls in automated tests are simulated. Follow `docs/youtube-local-upload.md` to configure a Google OAuth Web application, authorize the channel and run the first private upload.

No cloud deployment was performed. Uploads and connections are intentionally single-process and temporary: no restart recovery, automatic retries, public publishing, thumbnails, playlists or scheduling. Keep the local API running during transfer and check YouTube Studio before retrying an uncertain upload. Unchanged worker tests were not rerun for this integration.
