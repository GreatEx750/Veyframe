import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("application typography", () => {
  it("keeps the customer-facing screens on the shared readable type scale", () => {
    const css = readFileSync("src/app/studio.css", "utf8");

    expect(css).toContain("--font-ui-body: 14px;");
    expect(css).toContain("--font-ui-label: 13px;");
    expect(css).toContain("--font-ui-caption: 12px;");
    expect(css).toContain(".studio-shell .nav-item,\n.library-shell .nav-item");
    expect(css).toContain(".editor-mode-rail button {");
    expect(css).toContain("font-size: var(--font-ui-caption);");
  });
});
