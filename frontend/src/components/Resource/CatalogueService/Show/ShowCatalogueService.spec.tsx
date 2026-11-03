import type { ServiceTab } from "../../Generic/ServiceShow/ServiceShow";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ShowCatalogueService from "./ShowCatalogueService";

const state = vi.hoisted(() => ({ isHarvestable: true }));
vi.mock("react-admin", async importOriginal => ({
  ...await importOriginal<typeof import("react-admin")>(),
  useRecordContext: () => ({ id: "catalogue", isHarvestable: state.isHarvestable }),
  useTranslate: () => (key: string) => key,
}));
vi.mock("../../Generic/ServiceShow/ServiceShow", () => ({
  default: ({ tabs }: { tabs: ServiceTab[] }) => tabs
    .filter(tab => ["HarvestingJob", "PeriodicHarvestingJob"].includes(tab.resource ?? ""))
    .map(tab => <section key={tab.resource}>{tab.content}</section>),
}));
vi.mock("../../Generic/ServiceShow/ServiceRelatedTab", () => ({
  default: () => <button>Create related job</button>,
}));

describe("catalogue harvesting tabs", () => {
  it("blocks both harvesting and schedule configuration for the internal catalogue", () => {
    state.isHarvestable = false;
    render(<ShowCatalogueService />);
    expect(screen.queryByRole("button", { name: "Create related job" })).not.toBeInTheDocument();
    expect(screen.getAllByText("harvestingSchedules.unavailable")).toHaveLength(2);
  });

  it("keeps the existing configuration screens for external catalogues", () => {
    state.isHarvestable = true;
    render(<ShowCatalogueService />);
    expect(screen.getAllByRole("button", { name: "Create related job" })).toHaveLength(2);
    expect(screen.queryByText("harvestingSchedules.unavailable")).not.toBeInTheDocument();
  });
});
