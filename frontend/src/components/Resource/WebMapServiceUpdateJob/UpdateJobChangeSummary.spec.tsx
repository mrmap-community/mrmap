import { AdminContext, RecordContextProvider } from "react-admin";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import UpdateJobChangeSummary from "./UpdateJobChangeSummary";

describe("update job change summary", () => {
  it("uses recorded job totals, including zero", () => {
    render(
      <AdminContext>
        <RecordContextProvider value={{ id: 2, changedLayers: 12, unchangedLayers: 204, addedLayers: 3, deletedLayers: 0 }}>
          <UpdateJobChangeSummary />
        </RecordContextProvider>
      </AdminContext>,
    );
    for (const [type, total] of Object.entries({ changedLayers: 12, unchangedLayers: 204, addedLayers: 3, deletedLayers: 0 })) {
      expect(screen.getByLabelText(`updateReview.summary.${type}: ${total}`)).toHaveTextContent(String(total));
    }
  });
  it.each([false, true])("keeps missing totals unknown (compact=%s)", compact => {
    render(
      <AdminContext>
        <RecordContextProvider value={{ id: 2 }}>
          <UpdateJobChangeSummary compact={compact} />
        </RecordContextProvider>
      </AdminContext>,
    );
    const region = screen.getByRole("region", { name: "updateReview.changeSummary" });
    expect(within(region).getAllByLabelText(/: —$/)).toHaveLength(compact ? 3 : 4);
    expect(within(region).queryByLabelText(/: 0$/)).not.toBeInTheDocument();
  });
});
