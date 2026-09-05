import { GenerationProgress } from "./progress";
export default async function GenerationPage({ params, searchParams }: { params: Promise<{ projectId: string }>; searchParams: Promise<{ preview?: string }> }) {
  const { projectId } = await params;
  return <GenerationProgress projectId={projectId} preview={(await searchParams).preview === "first-five"} />;
}
