/**
 * Marks the lines the source editor changed against the served document (#1247).
 *
 * The alignment is the classic longest common subsequence over lines: a line
 * of the current text is reported when the LCS cannot explain it as an
 * unchanged line. Lines which merely MOVED — an inserted block above them —
 * still have their counterpart in the base and stay unmarked, which is what
 * the screen's changed-lines indicator promises. The common head and tail
 * are skipped before the table is built; when the differing middle is too
 * large for the quadratic table every middle line is reported — honest, and
 * not a memory bomb on a megabyte document.
 */

const MAX_TABLE_CELLS = 4_000_000;

export const changedLinesOf = (base: string, current: string): number[] => {
  if (base === current) return [];
  const baseLines = base.split("\n");
  const currentLines = current.split("\n");
  let head = 0;
  while (
    head < baseLines.length &&
    head < currentLines.length &&
    baseLines[head] === currentLines[head]
  ) {
    head += 1;
  }
  let baseEnd = baseLines.length;
  let currentEnd = currentLines.length;
  while (
    baseEnd > head &&
    currentEnd > head &&
    baseLines[baseEnd - 1] === currentLines[currentEnd - 1]
  ) {
    baseEnd -= 1;
    currentEnd -= 1;
  }
  const middle = baseLines.slice(head, baseEnd);
  const edited = currentLines.slice(head, currentEnd);
  const changed = new Set<number>();
  if (middle.length * edited.length > MAX_TABLE_CELLS) {
    for (let index = head; index < currentEnd; index += 1) {
      changed.add(index + 1);
    }
    return [...changed].sort((one, other) => one - other);
  }
  // suffix table: lengths[i * widths + j] = LCS length of middle[i..], edited[j..]
  const widths = edited.length + 1;
  const lengths = new Uint32Array((middle.length + 1) * widths);
  for (let i = middle.length - 1; i >= 0; i -= 1) {
    for (let j = edited.length - 1; j >= 0; j -= 1) {
      lengths[i * widths + j] =
        middle[i] === edited[j]
          ? lengths[(i + 1) * widths + j + 1] + 1
          : Math.max(lengths[(i + 1) * widths + j], lengths[i * widths + j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  while (i < middle.length && j < edited.length) {
    if (middle[i] === edited[j]) {
      i += 1;
      j += 1;
    } else if (lengths[(i + 1) * widths + j] >= lengths[i * widths + j + 1]) {
      i += 1; // a base line dropped from the document — nothing to mark
    } else {
      changed.add(head + j + 1); // a current line the base cannot explain
      j += 1;
    }
  }
  while (j < edited.length) {
    changed.add(head + j + 1);
    j += 1;
  }
  return [...changed].sort((one, other) => one - other);
};
