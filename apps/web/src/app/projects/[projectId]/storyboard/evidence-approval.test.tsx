import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { EvidenceApproval } from "./evidence-approval";
const fixture = { project_id: "p1", storyboard_version: 1, fingerprint: "a".repeat(64),
  claims: [{ id: "c1", scene_id: "s1", text: "Revenue doubled", status: "unverified", source_ids: [], explanation: "No support" }],
  sources: [], unverified_count: 1, approved: false, approval_required: true };
afterEach(() => vi.unstubAllGlobals());
it("requires acknowledgement before approving the exact saved fingerprint", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(fixture)).mockResolvedValueOnce(Response.json({ ...fixture, approved: true }));
  vi.stubGlobal("fetch", fetcher);
  render(<EvidenceApproval projectId="p1" version={1} />);
  const button = await screen.findByRole("button", { name: "Approve this storyboard and continue generation" });
  expect(button).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(button);
  await screen.findByText(/Saved storyboard v1 approved/);
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ expected_version: 1, fingerprint: fixture.fingerprint, acknowledge_unverified: true });
});
it("cannot approve unsaved edits", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(fixture)));
  render(<EvidenceApproval projectId="p1" version={1} disabled />);
  fireEvent.click(await screen.findByRole("checkbox"));
  expect(screen.getByRole("button", { name: "Approve this storyboard and continue generation" })).toBeDisabled();
});
