import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StoryboardEditor } from "./storyboard-editor";

const storyboard = {
  id: "storyboard-1",
  project_id: "project-1",
  version: 1,
  total_duration_seconds: 30,
  status: "draft" as const,
  scenes: [
    scene("scene-1", 0, "Dashboard", "Original dashboard narration", 10),
    scene("scene-2", 1, "Insights", "Original insights narration", 20),
  ],
};

function scene(id: string, order: number, title: string, narration: string, duration: number) {
  return {
    id,
    storyboard_id: "storyboard-1",
    order,
    title,
    objective: `Show ${title}`,
    narration,
    source_ids: ["source-1"],
    capture_plan: {
      start_url: "https://example.com",
      actions: [],
      success_assertions: [],
      timeout_seconds: 30,
    },
    expected_evidence: [title],
    duration_seconds: duration,
  };
}

function savingFetch() {
  return vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method !== "PUT") return { ok: false, json: async () => ({ detail: "No evidence fixture" }) };
    const payload = JSON.parse(String(init?.body)) as { scenes: typeof storyboard.scenes };
    return {
      ok: true,
      json: async () => ({
        ...storyboard,
        version: storyboard.version + 1,
        scenes: payload.scenes.map((item, order) => ({ ...item, order })),
        total_duration_seconds: payload.scenes.reduce(
          (total, item) => total + item.duration_seconds,
          0,
        ),
      }),
    };
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("StoryboardEditor", () => {
  it("reorders scenes and persists the new order as another version", async () => {
    const fetchMock = savingFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<StoryboardEditor initialStoryboard={storyboard} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Move Dashboard down" }));

    await screen.findByText("Saved version 2");
    const request = fetchMock.mock.calls.find((call) => call[1]?.method === "PUT")![1] as RequestInit;
    const payload = JSON.parse(String(request.body)) as { expected_version: number; scenes: Array<{ id: string }> };
    expect(payload.expected_version).toBe(1);
    expect(payload.scenes.map((item) => item.id)).toEqual(["scene-2", "scene-1"]);
    expect(screen.getAllByRole("heading", { level: 2 })[0]).toHaveTextContent("Insights");
  });

  it("edits narration and deleting a scene updates total duration", async () => {
    const fetchMock = savingFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<StoryboardEditor initialStoryboard={storyboard} projectId="project-1" />);

    const narration = screen.getAllByLabelText("Narration")[0];
    fireEvent.change(narration, { target: { value: "Updated narration" } });
    fireEvent.blur(narration);
    await screen.findByText("Saved version 2");
    const editPayload = JSON.parse(String(fetchMock.mock.calls.find((call) => call[1]?.method === "PUT")![1]?.body)) as { scenes: Array<{ narration: string }> };
    expect(editPayload.scenes[0].narration).toBe("Updated narration");

    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    await waitFor(() => expect(screen.getByText("20 seconds")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "Dashboard" })).not.toBeInTheDocument();
  });
});
