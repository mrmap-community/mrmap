import { RecordContextProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RelativeDateField from "./RelativeDateField";

/** a moment the given distance before (negative: after) now - the field answers
 *  distances, so the spec names its moments as distances too */
const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const renderField = (record: Record<string, unknown>, fromRecordProp = false) =>
  render(
    <RecordContextProvider value={fromRecordProp ? undefined : { id: 1, ...record }}>
      <RelativeDateField
        source="endedAt"
        record={fromRecordProp ? ({ id: 1, ...record } as never) : undefined}
        locales="en"
      />
    </RecordContextProvider>,
  );

describe("RelativeDateField", () => {
  it("answers the distance to now by the coarsest unit which holds it", () => {
    const { unmount } = renderField({ endedAt: ago(3 * HOUR) });
    expect(screen.getByText("3 hours ago")).toBeInTheDocument();
    unmount();
    renderField({ endedAt: ago(3 * DAY) });
    expect(screen.getByText("3 days ago")).toBeInTheDocument();
  });

  it("keeps the finest unit for a short distance and names the extremes", () => {
    const { unmount } = renderField({ endedAt: ago(30 * MINUTE) });
    expect(screen.getByText("30 minutes ago")).toBeInTheDocument();
    unmount();
    renderField({ endedAt: ago(DAY) });
    expect(screen.getByText("yesterday")).toBeInTheDocument();
    unmount();
    renderField({ endedAt: ago(-2 * HOUR) });
    expect(screen.getByText("in 2 hours")).toBeInTheDocument();
  });

  it("keeps the absolute moment readable in the title", () => {
    // far enough back to be answered by months, close enough to stay so while
    // the spec is run - the distance itself is not the point of this test
    const moment = ago(95 * DAY);
    renderField({ endedAt: moment });
    const field = screen.getByText(/ago/);
    expect(field).toHaveAttribute(
      "title",
      new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(moment)),
    );
  });

  it("answers nothing for a record which names no moment", () => {
    const { container, unmount } = renderField({});
    expect(container).toBeEmptyDOMElement();
    unmount();
    renderField({ endedAt: "" });
    expect(container).toBeEmptyDOMElement();
  });

  it("reads the record it is given beside the record of the screen", () => {
    renderField({ endedAt: ago(3 * HOUR) }, true);
    expect(screen.getByText("3 hours ago")).toBeInTheDocument();
  });
});
