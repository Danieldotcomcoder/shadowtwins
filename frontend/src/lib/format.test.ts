import { describe, expect, it } from "vitest";
import { fmtDuration } from "./format";

describe("fmtDuration", () => {
  it("reads well from seconds to a daily quota reset", () => {
    expect(fmtDuration(0.4)).toBe("0 s");
    expect(fmtDuration(45)).toBe("45 s");
    expect(fmtDuration(120)).toBe("2 min");
    expect(fmtDuration(3723.5)).toBe("62 min");
    expect(fmtDuration(3 * 3600)).toBe("3 h");
    expect(fmtDuration(3 * 3600 + 20 * 60)).toBe("3 h 20 min");
    expect(fmtDuration(null)).toBe("—");
    expect(fmtDuration(Number.NaN)).toBe("—");
  });
});
