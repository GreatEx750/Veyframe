import { TimelineEditor } from "./timeline-editor";

export default async function EditorPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <TimelineEditor projectId={projectId} />;
}
