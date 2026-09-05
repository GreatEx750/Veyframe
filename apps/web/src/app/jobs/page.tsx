import { JobsDashboard } from "./jobs-dashboard";

export default async function JobsPage({ searchParams }: {
  searchParams: Promise<{ job?: string | string[] }>;
}) {
  const query = await searchParams;
  const jobId = typeof query.job === "string" ? query.job : undefined;
  return <JobsDashboard key={jobId ?? "all-jobs"} jobId={jobId} />;
}
