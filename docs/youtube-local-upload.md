# Local YouTube uploads

Open a project with a completed, up-to-date export and choose **Upload to YouTube** beside Download MP4. This prototype uploads the actual saved export; it never generates another video or publishes publicly.

## Google setup

1. In the desired Google Cloud project, enable **YouTube Data API v3**.
2. Configure the Google Auth Platform consent screen. For a testing app, add your Google account as a test user. That account needs a YouTube channel.
3. Create an OAuth client with application type **Web application**. Register this exact authorized redirect URI: `http://localhost:3000/api/youtube/callback`.
4. In the root `.env`, set:

   ```dotenv
   YOUTUBE_LOCAL_ENABLED=true
   YOUTUBE_CLIENT_ID=your-web-client-id
   YOUTUBE_CLIENT_SECRET=your-web-client-secret
   ```

   Use OAuth credentials, not your Gemini API key. Never commit `.env` or paste the secret into a public issue. The existing `.gitignore` excludes `.env` files.

5. Restart the local API. Run the web app at **http://localhost:3000**, not an alternative hostname or port. Sign in to Veyframe, then open a completed project.
6. Choose Upload to YouTube → Connect YouTube. Grant upload and read-only YouTube permissions. Read-only access identifies the destination channel so you can review it before upload.
7. Verify the displayed channel, title, description and made-for-kids choice. Confirm that you have permission to upload, then select **Confirm private upload**.
8. Follow transfer progress and open the returned YouTube link. YouTube processing can continue after transfer completes. Review any other applicable YouTube Studio disclosures before publishing.

Google restricts uploads from unaudited API projects to private viewing. See [videos.insert requirements](https://developers.google.com/youtube/v3/docs/videos/insert). Public/unlisted publishing and API approval are outside this prototype.

## Local boundaries

- Requires a real Veyframe session even when other local routes allow anonymous development. All project and export ownership is checked.
- Google access tokens stay in API process memory, scoped to the Veyframe session. No refresh tokens are requested or persisted. Reconnect after token expiry (typically about an hour), logout/new session or API restart.
- Disconnect revokes the Google token and removes the local connection. Google account permissions can also be revoked in Google Account settings.
- Uses Google's resumable protocol in bounded chunks; one upload at a time per session. Progress measures confirmed bytes, not YouTube processing.
- Uploading the same export again returns its existing job within the same local process/session, including failed or uncertain jobs. No automatic retries are performed.
- Upload jobs are temporary, not durable. Keep the API running during transfer. If it restarts or an upload result is uncertain, check YouTube Studio before trying again to avoid duplicates. A page refresh in the same browser session retains the last job ID, not credentials.
- Cloud Run is explicitly disabled. Multi-worker hosting, durable credential storage, restart recovery and public publishing need a separate production integration.
- Existing generated captions/audio remain baked into the MP4. Separate caption-track upload, thumbnails, scheduling and playlists are not included.

Implementation follows Google's [web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server) and [resumable upload protocol](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol).
