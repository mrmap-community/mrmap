import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { AdminContext, testDataProvider } from "react-admin";
import { describe, expect, it, vi } from "vitest";
import UpdateJobChangeSummary from "./UpdateJobChangeSummary";

describe("update job change summary", () => {
  it("uses server totals rather than the returned page length, including zero", async () => {
    const totals: Record<string, number> = {
      modified: 12,
      unchanged: 204,
      added: 3,
      removed: 0,
    };
    const getList = vi
      .fn()
      .mockImplementation((_resource, params) =>
        Promise.resolve({ data: [], total: totals[params.filter.change_type] }),
      );
    render(
      <AdminContext
        queryClient={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
        dataProvider={testDataProvider({ getList })}
      >
        <UpdateJobChangeSummary jobId={2} serviceId="service" />
      </AdminContext>,
    );
    for (const [type, total] of Object.entries(totals)) {
      expect(
        await screen.findByLabelText(`updateReview.summary.${type}: ${total}`),
      ).toHaveTextContent(String(total));
      expect(getList).toHaveBeenCalledWith(
        "HistoricalLayer",
        expect.objectContaining({
          filter: {
            history_change_reason: "updatejob_id: 2",
            service: "service",
            change_type: type,
          },
          pagination: { page: 1, perPage: 1 },
        }),
      );
    }
  });
  it.each([false, true])(
    "does not show failed counts as zero (compact=%s)",
    async (compact) => {
      const getList = vi.fn().mockRejectedValue(new Error("Offline"));
      render(
        <AdminContext
          queryClient={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
          dataProvider={testDataProvider({ getList })}
        >
          <UpdateJobChangeSummary
            jobId={2}
            serviceId="service"
            compact={compact}
          />
        </AdminContext>,
      );
      const region = screen.getByRole("region", {
        name: "updateReview.changeSummary",
      });
      await waitFor(
        () =>
          expect(
            within(region).getAllByText("updateReview.countLoadError"),
          ).toHaveLength(compact ? 3 : 4),
        { timeout: 10000 },
      );
      expect(within(region).queryByText("0")).not.toBeInTheDocument();
    },
  );
});
