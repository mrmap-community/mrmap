import type { ReactNode } from "react";
import {
  AdminContext,
  BasenameContextProvider,
  ListContextProvider,
  type RaRecord,
  ResourceContextProvider,
  useList,
  testDataProvider,
} from "react-admin";

import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MonitoringRunsList from "./MonitoringRuns/MonitoringRunsList";
import UpdateJobsList from "./UpdateJobs/UpdateJobsList";

import "@testing-library/jest-dom/vitest";

const RunList = ({
  data,
  children,
}: {
  data: RaRecord[];
  children: ReactNode;
}) => {
  const context = useList({ data });
  return <ListContextProvider value={context}>{children}</ListContextProvider>;
};
const renderList = (data: RaRecord[], children: ReactNode, basename: string, resource = "WebMapServiceMonitoringRun") =>
  render(
    <AdminContext>
      <ResourceContextProvider value={resource}>
        <BasenameContextProvider basename={basename}>
          <RunList data={data}>{children}</RunList>
        </BasenameContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );
const dates = {
  dateCreated: "2026-09-30T12:00:00Z",
  dateDone: "2026-09-30T12:00:12Z",
  doneAt: "2026-09-30T12:00:12Z",
};

describe.each(["", "/WebMapService/service-1/show"])(
  "dashboard run lists with basename %s",
  (basename) => {
    it("links each monitoring run to its own details", () => {
      renderList(
        [
          {
            id: "run-1",
            ...dates,
            success: true,
            getMapProbeResults: [{ id: 1 }],
            getCapabilititesProbeResults: [{ id: 2 }],
          },
          { id: "run-2", ...dates, success: false },
        ],
        <MonitoringRunsList />,
        basename,
      );
      expect(
        screen.getAllByRole("link").map((link) => link.getAttribute("href")),
      ).toEqual([
        "#/WebMapServiceMonitoringRun/run-1/show",
        "#/WebMapServiceMonitoringRun/run-2/show",
      ]);
      expect(screen.getByText(/2 checks · 12.00 s/)).toBeInTheDocument();
      expect(screen.getByText(/0 checks · 12.00 s/)).toBeInTheDocument();
    });
    it("links update jobs to details and formats layer change counts", () => {
      renderList(
        [
          {
            id: 1,
            ...dates,
            status: "Review required",
            statusCode: 2,
            mappings: [{ id: 1, oldLayer: { id: 1 } }],
          },
          { id: 2, ...dates, status: "Updated", statusCode: 3 },
        ],
        <UpdateJobsList />,
        basename,
        "WebMapServiceUpdateJob",
      );
      expect(
        screen.getAllByRole("link").map((link) => link.getAttribute("href")),
      ).toEqual([
        "#/WebMapServiceUpdateJob/1/show",
        "#/WebMapServiceUpdateJob/2/show",
      ]);
      expect(
        screen.getByText(
          "Review required · 1 layer(s) are marked for deletion",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("Updated")).toBeInTheDocument();
    });
  },
);

it("shows recorded changes for each completed job even after mappings are removed", async () => {
  const getList = vi.fn().mockImplementation((_resource, params) =>
    Promise.resolve({
      data: [],
      total: params.filter.history_change_reason === "updatejob_id: 1" ? 12 : 0,
    }),
  );
  render(
    <AdminContext
      queryClient={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
      dataProvider={testDataProvider({ getList })}
    >
      <ResourceContextProvider value="WebMapServiceUpdateJob">
        <RunList
          data={[
            {
              id: 1,
              ...dates,
              status: "Updated",
              statusCode: 3,
              service: { id: "service-1" },
              changedLayers: 12, addedLayers: 12, deletedLayers: 12,
              mappings: [],
            },
            {
              id: 2,
              ...dates,
              status: "Updated",
              statusCode: 3,
              service: { id: "service-1" },
              changedLayers: 0, addedLayers: 0, deletedLayers: 0,
              mappings: [],
            },
          ]}
        >
          <UpdateJobsList />
        </RunList>
      </ResourceContextProvider>
    </AdminContext>,
  );
  for (const type of ["changedLayers", "addedLayers", "deletedLayers"]) {
    expect(
      await screen.findByLabelText(`updateReview.summary.${type}: 12`),
    ).toBeInTheDocument();
    expect(
      await screen.findByLabelText(`updateReview.summary.${type}: 0`),
    ).toBeInTheDocument();
  }
  expect(getList).not.toHaveBeenCalled();
  expect(
    screen.queryByText("updateReview.summaryScope"),
  ).not.toBeInTheDocument();
});
