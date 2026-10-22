import { AdminContext, RecordContextProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ServiceAlertChips from "./ServiceAlertChips";

import "@testing-library/jest-dom/vitest";

const renderChips = (record: Record<string, unknown>) =>
  render(
    <AdminContext>
      <RecordContextProvider value={record}>
        <ServiceAlertChips />
      </RecordContextProvider>
    </AdminContext>,
  );

describe("ServiceAlertChips", () => {
  it("names every state of the service which needs attention", () => {
    renderChips({
      id: "wms-1",
      monitoringFailed: true,
      updateReviewRequired: true,
    });
    expect(
      screen.getByText("serviceAttention.shortLabels.monitoringFailed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceAttention.shortLabels.updateReviewRequired"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("serviceAttention.shortLabels.noAlerts"),
    ).not.toBeInTheDocument();
  });

  it("answers a service which needs nothing without an alert", () => {
    renderChips({ id: "wms-1", monitoringFailed: false });
    expect(
      screen.getByText("serviceAttention.shortLabels.noAlerts"),
    ).toBeInTheDocument();
  });

  it("does not answer a state a kind of service cannot have", () => {
    render(
      <AdminContext>
        <ServiceAlertChips
          record={{ id: "wms-1", harvestAborted: undefined }}
        />
      </AdminContext>,
    );
    expect(
      screen.queryByText("serviceAttention.shortLabels.harvestAborted"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("serviceAttention.shortLabels.noAlerts"),
    ).toBeInTheDocument();
  });
});
