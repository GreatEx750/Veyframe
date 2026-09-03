import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";

import { proxy } from "./proxy";

const originalAuthSetting = process.env.DEMO_AUTH_REQUIRED;

afterEach(() => {
  if (originalAuthSetting === undefined) delete process.env.DEMO_AUTH_REQUIRED;
  else process.env.DEMO_AUTH_REQUIRED = originalAuthSetting;
});

describe("application route access", () => {
  it("keeps local optional-auth routes directly accessible", () => {
    delete process.env.DEMO_AUTH_REQUIRED;

    const response = proxy(new NextRequest("http://localhost:3000/projects/project-1/editor"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects signed-out users when production auth is required", () => {
    process.env.DEMO_AUTH_REQUIRED = "true";

    const response = proxy(new NextRequest("https://app.example.com/projects"));

    expect(response.headers.get("location")).toBe("https://app.example.com/login");
  });

  it("allows an authenticated request when production auth is required", () => {
    process.env.DEMO_AUTH_REQUIRED = "true";
    const request = new NextRequest("https://app.example.com/projects", {
      headers: { cookie: "demodirector_session=session-token" },
    });

    const response = proxy(request);

    expect(response.headers.get("location")).toBeNull();
  });
});
