import { RecordContextProvider } from "react-admin";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  messageKeyOf,
  stateColorOf,
  stateKeyOf,
  UpdateJobStatusChip,
} from "./UpdateJobState";

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

  it("explains the states with sentences, reusing the review wording where it fits", () => {
    expect(messageKeyOf(2)).toBe(
      "resources.CatalogueServiceUpdateJob.reviewRequiredMessage",
    );
    // every state which did not end shares the one sentence
    expect(messageKeyOf(1)).toBe(
      "resources.CatalogueServiceUpdateJob.notEndedMessage",
    );
    expect(messageKeyOf(4)).toBe(
      "resources.CatalogueServiceUpdateJob.notEndedMessage",
    );
    // the ended states reuse the wording of a web map service update review
    expect(messageKeyOf(3)).toBe("updateReview.failedMessage");
    expect(messageKeyOf(5)).toBe("updateReview.completedMessage");
    expect(messageKeyOf(42)).toBeNull();
    expect(messageKeyOf(undefined)).toBeNull();
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
