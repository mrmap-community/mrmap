import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { AdminContext, testDataProvider } from "react-admin";
import { describe, expect, it, vi } from "vitest";

import ShowWebMapServiceMonitoringRun from "./ShowWebMapServiceMonitoringRun";

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: ({
    resource,
    relatedResource,
  }: {
    resource: string;
    relatedResource: { resource: string; id: string };
  }) => (
    <div>
      {resource} for {relatedResource.resource}/{relatedResource.id}
    </div>
  ),
}));

describe("monitoring run details", () => {
  it("loads the selected run and scopes both result lists to it", async () => {
    const getOne = vi.fn().mockResolvedValue({
      data: {
        id: "run-1",
        success: true,
        dateCreated: "2026-09-30T12:00:00Z",
        dateDone: "2026-09-30T12:00:12Z",
      },
    });
    render(
      <AdminContext dataProvider={testDataProvider({ getOne })}>
        <ShowWebMapServiceMonitoringRun
          resource="WebMapServiceMonitoringRun"
          id="run-1"
        />
      </AdminContext>,
    );
    expect(
      await screen.findByText(
        "GetCapabilitiesProbeResult for WebMapServiceMonitoringRun/run-1",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "GetMapProbeResult for WebMapServiceMonitoringRun/run-1",
      ),
    ).toBeInTheDocument();
    expect(getOne).toHaveBeenCalledWith(
      "WebMapServiceMonitoringRun",
      expect.objectContaining({ id: "run-1" }),
    );
  });
});
