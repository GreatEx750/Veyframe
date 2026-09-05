import { describe, expect, it } from "vitest";
import { longFormVideoPlanSchema } from "./longform";

describe("long-form contracts", () => {
  it("rejects plans that are not exactly three minutes", () => {
    expect(() => longFormVideoPlanSchema.parse({ duration_ms: 179000 })).toThrow();
  });
  it("exports the fixed proof-first duration", () => {
    expect(longFormVideoPlanSchema.shape.duration_ms.parse(180000)).toBe(180000);
  });
});
