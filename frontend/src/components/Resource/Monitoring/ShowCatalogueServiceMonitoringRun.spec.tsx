import { AdminContext, testDataProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ShowCatalogueServiceMonitoringRun from "./ShowCatalogueServiceMonitoringRun";

import "@testing-library/jest-dom/vitest";

vi.mock("./MonitoringProbeResults", () => ({
  default: ({
    groups,
  }: {
    groups: { resource: string; type: string; ids: string[] }[];
  }) => (
    <div>
      {groups.map((group) => (
        <span key={group.resource}>
          {group.resource}:{group.type}:{group.ids.join(",")}
        </span>
      ))}
    </div>
  ),
}));

describe("csw monitoring run details", () => {
  it("maps the results of a run to the probe results of the csw", async () => {
    const getOne = vi.fn().mockResolvedValue({
      data: {
        id: "run-1",
        success: false,
        dateCreated: "2026-09-30T12:00:00Z",
        dateDone: "2026-09-30T12:00:12Z",
        getCapabilitiesProbeResults: [{ id: "c1" }],
        getRecordsProbeResults: [{ id: "r1" }, { id: "r2" }],
        setting: null,
      },
    });
    render(
      <AdminContext dataProvider={testDataProvider({ getOne })}>
        <ShowCatalogueServiceMonitoringRun
          resource="CatalogueServiceMonitoringRun"
          id="run-1"
        />
      </AdminContext>,
    );
    expect(
      await screen.findByText(
        "CatalogueServiceGetCapabilitiesProbeResult:GetCapabilities:c1",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "CatalogueServiceGetRecordsProbeResult:GetRecords:r1,r2",
      ),
    ).toBeInTheDocument();
  });
});