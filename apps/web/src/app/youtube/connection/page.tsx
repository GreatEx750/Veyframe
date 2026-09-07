import Link from "next/link";

export default function YouTubeConnectionResult() {
  return <main className="editor-state-shell"><section className="editor-load-state">
    <h1>YouTube connection was not completed</h1>
    <p>No video was uploaded. Google consent may have been cancelled, expired or missing a required permission.</p>
    <p>Return to your project, choose Upload to YouTube, then connect again. Make sure your Google account has a YouTube channel and is an OAuth test user.</p>
    <Link href="/projects">Return to Projects</Link>
  </section></main>;
}
