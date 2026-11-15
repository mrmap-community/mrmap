import { describe, expect, it } from "vitest";

import { changedLinesOf } from "./changedLines";

const doc = (lines: string[]) => lines.join("\n");

describe("changedLinesOf", () => {
  it("reports nothing for identical text", () => {
    expect(changedLinesOf(doc(["a", "b", "c"]), doc(["a", "b", "c"]))).toEqual(
      [],
    );
  });

  it("reports the edited line alone", () => {
    expect(changedLinesOf(doc(["a", "b1", "c"]), doc(["a", "b2", "c"]))).toEqual(
      [2],
    );
  });

  it("marks the inserted lines and keeps the moved lines unmarked", () => {
    expect(
      changedLinesOf(doc(["a", "c"]), doc(["a", "x", "y", "c"])),
    ).toEqual([2, 3]);
  });

  it("marks nothing in the surviving lines when a block was deleted", () => {
    expect(changedLinesOf(doc(["a", "x", "y", "c"]), doc(["a", "c"]))).toEqual(
      [],
    );
  });

  it("marks an appended line", () => {
    expect(changedLinesOf(doc(["a", "b"]), doc(["a", "b", "c"]))).toEqual([3]);
  });

  it("aligns repeated lines, marking only the changed occurrence", () => {
    expect(changedLinesOf(doc(["b", "b", "b"]), doc(["b", "B", "b"]))).toEqual(
      [2],
    );
  });

  it("marks every line of a differing middle too large for the table", () => {
    const base = doc(["a", ...Array.from({ length: 3000 }, (_, i) => `x${i}`), "z"]);
    const current = doc([
      "a",
      ...Array.from({ length: 3000 }, (_, i) => `y${i}`),
      "z",
    ]);
    const changed = changedLinesOf(base, current);
    expect(changed.length).toBeGreaterThanOrEqual(3000);
    expect(changed[0]).toBe(2);
  });
});
