import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { JobsDashboard } from "./jobs-dashboard";
import JobsPage from "./page";

const now = "2026-09-05T14:00:00Z";
const entry = {
  job: { id: "job-1", project_id: "project-1", status: "queued", stage: "inspection", completed_stages: [], attempts: 0, version: 1, created_at: now, updated_at: now, lease_until: null, message: "Queued for inspection", export_id: null, timeline_version: null },
  project_name: "Wikipedia walkthrough", kind: "generation", elapsed_seconds: 1800, step_elapsed_seconds: 1800,
  last_progress_at: now, heartbeat_at: null, health: "queued", health_message: "No worker has claimed this job.",
  eta_min_seconds: null, eta_max_seconds: null, estimate_basis: "No reliable estimate until a worker starts.", events: [],
};
function mockEntry(value = entry) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [value], active_count: 1, maximum_active: 1, server_time: now }) }));
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("retries a full presentation through its authored slide pipeline", async () => {
  const failed = { ...entry, kind: "presentation", job: { ...entry.job, status: "failed", attempts: 1 } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [failed], active_count: 0, maximum_active: 1, server_time: now }) }));
  render(<JobsDashboard />);
  expect(await screen.findByText(/Presentation · 2 minutes/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "Approve retry"}));
  expect(fetch).toHaveBeenCalledWith("/api/projects/project-1/generation/presentation", expect.objectContaining({method: "POST"}));
});

it("requires an explicit rebuild action for a completed presentation", async () => {
  const complete = { ...entry, kind: "presentation", job: { ...entry.job, status: "succeeded", stage: "done", attempts: 2 } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [complete], active_count: 0, maximum_active: 1, server_time: now }) }));
  render(<JobsDashboard />);
  fireEvent.click(await screen.findByRole("button", {name: "Rebuild from saved slides"}));
  expect(fetch).toHaveBeenCalledWith("/api/projects/project-1/generation/presentation", expect.objectContaining({
    method: "POST", body: JSON.stringify({approved: true, rebuild: true}),
  }));
});

it("selects the requested job rather than the first job in the list", async () => {
  const created = { ...entry, project_name: "New demo", job: { ...entry.job, id: "new-job", message: "Starting your new demo" } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [entry, created], active_count: 1, maximum_active: 1, server_time: now }) }));
  render(await JobsPage({ searchParams: Promise.resolve({ job: "new-job" }) }));
  expect(await screen.findByRole("heading", { name: "New demo" })).toBeInTheDocument();
  expect(screen.queryByText("Queued for inspection")).not.toBeInTheDocument();
});

it("waits for a newly created job to appear without displaying an unrelated job", async () => {
  vi.useFakeTimers();
  const created = { ...entry, project_name: "New demo", job: { ...entry.job, id: "new-job", message: "New demo queued" } };
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ jobs: [entry], active_count: 1, maximum_active: 1, server_time: now }) })
    .mockResolvedValue({ ok: true, json: async () => ({ jobs: [entry, created], active_count: 1, maximum_active: 1, server_time: now }) }));
  await act(async () => { render(<JobsDashboard jobId="new-job" />); });
  expect(screen.getByText(/Waiting for the selected job/)).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Selected job details" })).not.toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(screen.getByRole("heading", { name: "New demo" })).toBeInTheDocument();
});

it("shows stalled queue details without inventing an ETA or progress", async () => {
  mockEntry(); render(<JobsDashboard />);
  expect(await screen.findByText("No worker has claimed this job.")).toBeInTheDocument();
  expect(screen.getByText("Not currently estimable")).toBeInTheDocument();
  expect(screen.getByText("1 active · Maximum 1 generation per account")).toBeInTheDocument();
  expect(screen.getByText(/Earlier activity was not recorded/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve retry" })).not.toBeInTheDocument();
});

it("shows timestamped worker logs and explicit retry approval for a failed preview", async () => {
  const failed = { ...entry, kind: "presentation_preview", health: "finished", job: { ...entry.job, status: "failed", stage: "render", attempts: 1, message: "Render timed out" }, events: [{ sequence: 1, at: now, stage: "render", level: "error", message: "Renderer timed out; saved slides preserved." }] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [failed], active_count: 0, maximum_active: 1, server_time: now }) }));
  render(<JobsDashboard />);
  expect(await screen.findByText("Error: Renderer timed out; saved slides preserved.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Approve retry" })).toBeEnabled();
  expect(screen.getByText(/Unsaved provider calls may be charged again/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Job identifiers"));
  expect(screen.getByText("project-1")).toBeInTheDocument();
});

it("shows a connection error rather than an empty or apparently healthy job list", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  render(<JobsDashboard />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Live updates are disconnected");
  expect(screen.queryByText("No generation jobs yet")).not.toBeInTheDocument();
});

it("re-sends a queued job without approving paid retries or creating a new job", async () => {
  mockEntry(); render(<JobsDashboard />);
  fireEvent.click(await screen.findByRole("button", { name: "Re-send to worker" }));
  expect(fetch).toHaveBeenCalledWith("/api/projects/project-1/generation/job-1/retry", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: false }),
  });
});

it("polls new activity and keeps the last saved status when the connection fails", async () => {
  vi.useFakeTimers();
  const update = { ...entry, job: { ...entry.job, message: "Recording browser actions" }, events: [{ sequence: 1, at: now, stage: "capture", level: "info", message: "Captured click 1" }] };
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ jobs: [entry], active_count: 1, maximum_active: 1, server_time: now }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ jobs: [update], active_count: 1, maximum_active: 1, server_time: now }) })
    .mockResolvedValue({ ok: false, status: 503 });
  vi.stubGlobal("fetch", fetchMock);
  await act(async () => { render(<JobsDashboard />); });
  expect(screen.getByText("Queued for inspection")).toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(screen.getByText("Captured click 1")).toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(screen.getByRole("alert")).toHaveTextContent("disconnected");
  expect(screen.getByText("Recording browser actions")).toBeInTheDocument();
});
