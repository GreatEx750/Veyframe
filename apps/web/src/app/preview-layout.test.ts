import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("editor video preview", () => {
  it("shows the complete rendered 16:9 frame without cropping it", () => {
    const css = readFileSync("src/app/styles.css", "utf8");

    expect(css).toContain(".editor-preview-player");
    expect(css).toContain("aspect-ratio: 16 / 9");
    expect(css).toMatch(
      /\.preview-template-rendered \.preview-video-frame video \{[^}]*object-fit: contain;/,
    );
    expect(css).not.toMatch(
      /\.preview-template-rendered \.preview-video-frame video \{[^}]*object-fit: cover;/,
    );
    expect(css).toMatch(
      /\.preview-template-soft_frame \.preview-video-frame, \.preview-template-spotlight \.preview-video-frame \{[^}]*border-radius: 12px;/,
    );
  });
});
