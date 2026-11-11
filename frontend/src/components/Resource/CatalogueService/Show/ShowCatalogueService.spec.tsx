import type { ServiceTab } from "../../Generic/ServiceShow/ServiceShow";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ShowCatalogueService from "./ShowCatalogueService";

/** The props one related-tab screen of the tabs is rendered with. */
interface RelatedTabProps {
  resource?: string
  defaultSelectedColumns?: string[]
  updateFieldDefinitions?: { props: { source: string } & Record<string, unknown> }[]
}

const state = vi.hoisted(() => ({ isHarvestable: true }));
/** The props the harvesting and schedule screens of the tabs are rendered with. */
const relatedTabs = vi.hoisted(() => ({
  props: [] as RelatedTabProps[],
}));
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
  default: (props: RelatedTabProps) => {
    relatedTabs.props.push(props);
    return <button>Create related job</button>;
  },
}));

beforeEach(() => {
  relatedTabs.props = [];
});

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

  it("declares the harvesting runs by the creation time the api answers, titled in the user's language", () => {
    state.isHarvestable = true;
    render(<ShowCatalogueService />);
    const runs = relatedTabs.props.find(props => props.resource === "HarvestingJob");
    // `createdAt` is no field of a harvesting job - the column it declared stayed
    // empty for every run (#1078)
    expect(runs?.defaultSelectedColumns).toEqual(
      expect.arrayContaining(["id", "phase", "progress", "dateCreated", "doneAt"]),
    );
    expect(runs?.defaultSelectedColumns).not.toContain("createdAt");
    const dateCreated = runs?.updateFieldDefinitions
      ?.find(definition => definition.props.source === "dateCreated");
    expect(dateCreated?.props.label).toBe("harvestingActivity.started");
    expect(dateCreated?.props.emptyText).toBe("—");
  });
});
