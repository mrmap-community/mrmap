import { QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { AdminContext, testDataProvider } from "react-admin";
import { describe, expect, it, vi } from "vitest";
import MonitoringProbeResults from "./MonitoringProbeResults";

const renderResults = (
  getMany = vi.fn().mockImplementation((resource) =>
    Promise.resolve({
      data:
        resource === "GetMapProbeResult"
          ? [
              {
                id: "map",
                checkResponseImageSuccess: false,
                checkResponseImageMessage:
                  "Could not create image from response.",
                checkResponseDoesNotContainSuccess: true,
                checkResponseDoesNotContainMessage: "OK",
              },
              {
                id: "unknown",
                checkResponseImageSuccess: null,
                checkResponseDoesNotContainSuccess: null,
              },
            ]
          : [
              {
                id: "cap",
                checkResponseIsValidXmlSuccess: true,
                checkResponseDoesContainSuccess: true,
                checkResponseDoesNotContainSuccess: true,
              },
            ],
    }),
  ),
) => {
  render(
    <AdminContext
      queryClient={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
      dataProvider={testDataProvider({ getMany })}
    >
      <MonitoringProbeResults
        capabilitiesIds={["cap"]}
        mapIds={["map", "unknown"]}
      />
    </AdminContext>,
  );
  return getMany;
};
describe("monitoring probe cards", () => {
  it("loads exact result IDs, puts failures first and expands their explanation", async () => {
    const getMany = renderResults();
    await screen.findByText("monitoringRun.probeResults");
    expect(getMany).toHaveBeenCalledWith(
      "GetMapProbeResult",
      expect.objectContaining({ ids: ["map", "unknown"] }),
    );
    expect(getMany).toHaveBeenCalledWith(
      "GetCapabilitiesProbeResult",
      expect.objectContaining({ ids: ["cap"] }),
    );
    const cards = screen.getAllByRole("button", { expanded: true });
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveTextContent("GetMap");
    expect(
      screen.getByText("Could not create image from response."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /GetCapabilities/ }),
    ).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: /GetCapabilities/ }));
    expect(
      screen.getByText("monitoringRun.validXml · monitoringRun.passed"),
    ).toBeInTheDocument();
  });
  it("filters by probe status and does not mark absent checks as passed", async () => {
    renderResults();
    await screen.findByText("monitoringRun.probeResults");
    fireEvent.click(
      screen.getByRole("button", { name: "monitoringRun.failed" }),
    );
    expect(
      screen.queryByRole("button", { name: /GetCapabilities/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GetMap/ })).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "monitoringRun.notRecorded" }),
    );
    expect(screen.getByRole("button", { name: /unknown/ })).toHaveTextContent(
      "monitoringRun.notRecorded",
    );
    expect(
      screen.queryByText("Could not create image from response."),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "updateReview.all" }));
    expect(
      screen.getByRole("button", { name: /GetCapabilities/ }),
    ).toBeInTheDocument();
  });
  it("reports loading failures without showing misleading counts", async () => {
    renderResults(vi.fn().mockRejectedValue(new Error("Offline")));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "monitoringRun.resultsLoadError",
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("handles runs with no results without querying empty relationships", async () => {
    const getMany = vi.fn();
    render(
      <AdminContext dataProvider={testDataProvider({ getMany })}>
        <MonitoringProbeResults capabilitiesIds={[]} mapIds={[]} />
      </AdminContext>,
    );
    expect(screen.getByText("monitoringRun.noResults")).toBeInTheDocument();
    expect(getMany).not.toHaveBeenCalled();
  });
});
