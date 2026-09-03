import { StoryboardEditor } from "./storyboard-editor";

export default async function StoryboardPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <StoryboardEditor projectId={projectId} />;
}
