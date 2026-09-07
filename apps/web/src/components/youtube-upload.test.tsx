import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { YouTubeUpload } from "./youtube-upload";

beforeEach(() => {
  sessionStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("explains missing OAuth setup without offering an upload", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false, configured: false, connected: false, channel_title: null, message: "Local setup required" }) }));
  render(<YouTubeUpload projectId="p" exportId="e" title="My video" />);
  fireEvent.click(await screen.findByRole("button", { name: "Upload to YouTube" }));
  expect(await screen.findByText(/YouTube upload is not configured/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm private upload" })).not.toBeInTheDocument();
});

it("requires audience and confirmation and uploads only the selected saved export", async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: true, configured: true, connected: true, channel_title: "My channel", message: "Connected" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "job", export_id: "e", status: "succeeded", progress: 100, message: "Uploaded privately", video_id: "abcdefghijk" }) });
  vi.stubGlobal("fetch", fetchMock);
  render(<YouTubeUpload projectId="p" exportId="e" title="My video" />);
  fireEvent.click(await screen.findByRole("button", { name: "Upload to YouTube" }));
  expect(await screen.findByText("My channel")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "Confirm private upload" });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Is this video made for kids?"), { target: { value: "no" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(submit);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const body = JSON.parse(fetchMock.mock.calls[1][1].body);
  expect(body).toEqual({ export_id: "e", title: "My video", description: "", made_for_kids: false, confirmed: true });
  expect(await screen.findByRole("link", { name: "Open video on YouTube" })).toHaveAttribute("href", "https://www.youtube.com/watch?v=abcdefghijk");
  expect(screen.queryByRole("button", { name: "Confirm private upload" })).not.toBeInTheDocument();
});

it("shows the upload control wherever the project editor is hosted", async () => {
  render(<YouTubeUpload projectId="p" exportId="e" title="My video" />);
  expect(await screen.findByRole("button", { name: "Upload to YouTube" })).toBeInTheDocument();
});
