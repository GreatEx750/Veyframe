import { render, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { SessionBoundary } from "./session-boundary";

const navigation = vi.hoisted(() => ({ pathname: "/", replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => navigation,
}));
afterEach(() => {
  vi.unstubAllGlobals();
  navigation.replace.mockReset();
  navigation.refresh.mockReset();
});

it("returns stale protected sessions to login", async () => {
  navigation.pathname = "/projects";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "expired", session: null }),
  }));
  render(<SessionBoundary><div>Protected project</div></SessionBoundary>);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/login?reason=session_expired"));
  expect(navigation.refresh).toHaveBeenCalled();
});

it("renders the public landing page without contacting the session API", () => {
  navigation.pathname = "/";
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<SessionBoundary><main>Public landing</main></SessionBoundary>);
  expect(fetch).not.toHaveBeenCalled();
  expect(navigation.replace).not.toHaveBeenCalled();
});

it("still checks and rejects an expired Studio session", async () => {
  navigation.pathname = "/studio";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) }));
  render(<SessionBoundary><main>Studio</main></SessionBoundary>);
  await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/login?reason=session_expired"));
});

it.each([503, 429])("does not log out a user during a temporary %s failure", async (status) => {
  navigation.pathname = "/studio";
  const fetch = vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  const view = render(<SessionBoundary><main>Studio</main></SessionBoundary>);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(navigation.replace).not.toHaveBeenCalled();
  view.unmount();
});

it("preserves the session when the connection fails", async () => {
  navigation.pathname = "/studio";
  const fetch = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  vi.stubGlobal("fetch", fetch);
  const view = render(<SessionBoundary><main>Studio</main></SessionBoundary>);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(navigation.replace).not.toHaveBeenCalled();
  view.unmount();
});
