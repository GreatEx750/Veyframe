import { JobsDashboard } from "@/app/jobs/jobs-dashboard";

export function GenerationProgress({ projectId }: { projectId: string; preview?: boolean }) {
  return <JobsDashboard projectId={projectId} />;
}
