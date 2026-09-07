import data from "../../public/benchmarks/generation-2026-09-06.json";

export const benchmarkRuns = data.runs;
export const benchmarkMethodology = data;
export type BenchmarkRun = (typeof benchmarkRuns)[number];

export function elapsedSeconds(run: BenchmarkRun): number | null {
  if (!run.startedAt || !run.completedAt) return null;
  const seconds = Math.ceil((Date.parse(run.completedAt) - Date.parse(run.startedAt)) / 1000);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export function compareTime(generationSeconds: number | null, manualMinutes: number | null) {
  if (generationSeconds === null || !Number.isFinite(generationSeconds) || generationSeconds < 0) return null;
  if (manualMinutes === null || !Number.isFinite(manualMinutes) || manualMinutes < 1 || manualMinutes > 1440) return null;
  const totalSeconds = generationSeconds + data.veyframeBriefReviewMinutes * 60;
  const savedSeconds = Math.round(manualMinutes * 60 - totalSeconds);
  return { totalSeconds, savedSeconds, savedPercent: Math.round(savedSeconds / (manualMinutes * 60) * 100) };
}

export function formatTime(seconds: number): string {
  const value = Math.round(Math.abs(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  const remainder = value % 60;
  if (hours) return `${hours}h ${minutes}m${remainder ? ` ${remainder}s` : ""}`;
  return `${minutes}m${remainder ? ` ${remainder}s` : ""}`;
}
