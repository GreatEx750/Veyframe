import { GenerationProgress } from "./progress";
export default async function GenerationPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <GenerationProgress projectId={projectId} />;
}
