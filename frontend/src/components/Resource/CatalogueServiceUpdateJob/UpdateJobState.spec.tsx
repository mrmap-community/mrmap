import { RecordContextProvider } from "react-admin";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  stateColorOf,
  stateKeyOf,
  UpdateJobStatusChip,
  waitsFor,
} from "./UpdateJobState";

const translate = (key: string) => key;

describe("UpdateJobState", () => {
  it("names every state the api can answer, by its code", () => {
    expect(stateKeyOf(2)).toBe("reviewRequired");
    expect(stateKeyOf(5)).toBe("updated");
    expect(stateKeyOf(42)).toBeNull();
  });

  it("colours the states by the attention they ask for", () => {
    expect(stateColorOf(3)).toBe("error");
    expect(stateColorOf(2)).toBe("warning");
    expect(stateColorOf(0)).toBe("success");
    expect(stateColorOf(5)).toBe("success");
    expect(stateColorOf(1)).toBe("info");
    expect(stateColorOf(4)).toBe("info");
    expect(stateColorOf(undefined)).toBe("info");
  });

  it("says what a job which did not end waits for, and nothing for one which ended", () => {
    expect(waitsFor({ statusCode: 2 }, translate)).toBe(
      "resources.CatalogueServiceUpdateJob.waitsFor.reviewRequired",
    );
    expect(waitsFor({ statusCode: 4 }, translate)).toBe(
      "resources.CatalogueServiceUpdateJob.waitsFor.waitingForProcessing",
    );
    // an ended job waits for nothing, whatever state it ended in
    expect(
      waitsFor({ statusCode: 2, doneAt: "2026-11-01T00:00:00Z" }, translate),
    ).toBeNull();
    // a decided state asks for no wait either
    expect(waitsFor({ statusCode: 5 }, translate)).toBeNull();
  });

  it("shows the state of the job, as the api names it", () => {
    const { getByText } = render(
      <RecordContextProvider value={{ id: 3, status: "Review required", statusCode: 2 }}>
        <UpdateJobStatusChip />
      </RecordContextProvider>,
    );
    expect(getByText("Review required")).toBeInTheDocument();
  });
});
