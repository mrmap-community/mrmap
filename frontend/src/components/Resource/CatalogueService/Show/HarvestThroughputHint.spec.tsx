import { useGetList } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HarvestThroughputHint from "./HarvestThroughputHint";

vi.mock("react-admin", () => ({
  useGetList: vi.fn(() => ({ data: [] })),
  // the segments of a key and its interpolations are what a screen decides on
  useTranslate:
    () =>
    (key: string, options?: Record<string, unknown>) =>
      [
        key.split(".").pop(),
        ...Object.entries(options ?? {}).map(
          ([name, value]) => `${name}=${String(value)}`,
        ),
      ].join(" "),
}));

const runs = (data: unknown[]) =>
  vi.mocked(useGetList).mockReturnValue({
    data,
  } as unknown as ReturnType<typeof useGetList>);

beforeEach(() => {
  runs([]);
});

describe("the throughput the harvests of a catalogue measured", () => {
  it("asks the runs which ended last of the catalogue", () => {
    runs([{ id: "1", maxStepSize: 50, recordsPerMinute: 15 }]);
    render(<HarvestThroughputHint serviceId="csw-1" />);
    expect(useGetList).toHaveBeenCalledWith(
      "HarvestingJob",
      expect.objectContaining({
        filter: { service__id: "csw-1" },
        sort: { field: "doneAt", order: "DESC" },
      }),
    );
  });

  it("names the throughput of every size which was measured", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: 15 },
      { id: "2", maxStepSize: 25, recordsPerMinute: 30 },
    ]);
    render(<HarvestThroughputHint serviceId="csw-1" currentSize={50} />);
    expect(screen.getByText("perPage size=50 throughput=15")).toBeInTheDocument();
    expect(screen.getByText("perPage size=25 throughput=30")).toBeInTheDocument();
  });

  it("recommends the fastest measured size and says what it is based on", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: 15 },
      { id: "2", maxStepSize: 25, recordsPerMinute: 30 },
    ]);
    render(<HarvestThroughputHint serviceId="csw-1" currentSize={50} />);
    expect(screen.getByText("basis count=2")).toBeInTheDocument();
    expect(screen.getByText("recommendation size=25")).toBeInTheDocument();
  });

  it("says so when the size of the catalogue is already the fastest one", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: 15 },
      { id: "2", maxStepSize: 25, recordsPerMinute: 30 },
    ]);
    render(<HarvestThroughputHint serviceId="csw-1" currentSize={25} />);
    expect(screen.getByText("isFastest size=25")).toBeInTheDocument();
    expect(screen.queryByText(/recommendation/)).not.toBeInTheDocument();
  });

  it("averages the runs which asked the same size", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: 10 },
      { id: "2", maxStepSize: 50, recordsPerMinute: 20 },
    ]);
    render(<HarvestThroughputHint serviceId="csw-1" />);
    expect(screen.getByText("perPage size=50 throughput=15")).toBeInTheDocument();
    expect(screen.getByText("basis count=2")).toBeInTheDocument();
  });

  it("recommends nothing while no harvest of the catalogue finished", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: null },
      { id: "2", maxStepSize: 25, recordsPerMinute: null },
    ]);
    const { container } = render(
      <HarvestThroughputHint serviceId="csw-1" currentSize={50} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("names only the runs which measured something as its basis", () => {
    runs([
      { id: "1", maxStepSize: 50, recordsPerMinute: 15 },
      { id: "2", maxStepSize: 25, recordsPerMinute: null },
    ]);
    render(<HarvestThroughputHint serviceId="csw-1" />);
    expect(screen.getByText("basis count=1")).toBeInTheDocument();
  });

  it("answers its lines as spans, so an input can carry them as its helper text", () => {
    runs([{ id: "1", maxStepSize: 50, recordsPerMinute: 15 }]);
    render(<HarvestThroughputHint serviceId="csw-1" />);
    // a helper text is a paragraph: only spans may be its lines, and every one of
    // them is a line of its own and inherits the caption of that helper text
    [
      "basis count=1",
      "perPage size=50 throughput=15",
      "recommendation size=50",
      "measuredBy",
    ].forEach((line) => {
      expect(screen.getByText(line)).toHaveProperty("tagName", "SPAN");
      expect(screen.getByText(line)).toHaveStyle({ display: "block" });
    });
  });
});
