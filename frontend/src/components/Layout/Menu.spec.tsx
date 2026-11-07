import { useTranslate } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18nProvider from "../../providers/i18nProvider";
import CustomMenu from "./Menu";

import "@testing-library/jest-dom/vitest";

/** The CSW group as MrMapFrontend registers it: options.label defaults to the resource name. */
const resources = vi.hoisted(() => {
  const menuEntry = (name: string, group: string, order: number) => ({
    name,
    options: { label: name, menu: { group, order } },
  });
  return {
    CatalogueService: menuEntry("CatalogueService", "CSW", 10),
    HarvestingJob: menuEntry("HarvestingJob", "CSW", 20),
    CatalogueServiceUpdateJob: menuEntry("CatalogueServiceUpdateJob", "CSW", 40),
    // The System group entry names its label key explicitly instead of a resources block.
    ServiceAlert: {
      name: "ServiceAlert",
      options: {
        label: "serviceAlerts.title",
        menu: { group: "System", order: 5 },
      },
    },
    // A resource no resources block names keeps its name as it does today.
    Layer: menuEntry("Layer", "WMS", 20),
  };
});

// The menu renders its entries through these react-admin pieces; the test
// asserts the text the menu hands them, so they are replaced by their label.
vi.mock("react-admin", () => ({
  DashboardMenuItem: () => null,
  MenuItemLink: ({ primaryText }: { primaryText: string }) => (
    <span>{primaryText}</span>
  ),
  useResourceDefinitions: () => resources,
  useSidebarState: () => [true, vi.fn()],
  useTranslate: vi.fn(),
}));

describe.each([
  {
    locale: "de",
    catalogue: "Katalogdienste",
    harvesting: "Datenübernahmen",
    updateJobs: "Aktualisierungsaufträge der Katalogdienste",
    alerts: "Handlungsbedarf",
  },
  {
    locale: "en",
    catalogue: "Catalogue Service",
    harvesting: "Harvesting runs",
    updateJobs: "Catalogue service update jobs",
    alerts: "Attention required",
  },
])("menu in locale $locale", ({ locale, ...labels }) => {
  beforeEach(async () => {
    await i18nProvider.changeLocale(locale);
    vi.mocked(useTranslate).mockReturnValue(i18nProvider.translate);
  });

  it("names the CSW group entries by what they are, not by their class", () => {
    render(<CustomMenu />);

    expect(screen.getByText(labels.catalogue)).toBeInTheDocument();
    expect(screen.getByText(labels.harvesting)).toBeInTheDocument();
    expect(screen.getByText(labels.updateJobs)).toBeInTheDocument();
    expect(
      screen.queryByText("CatalogueService"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("HarvestingJob")).not.toBeInTheDocument();
    expect(
      screen.queryByText("CatalogueServiceUpdateJob"),
    ).not.toBeInTheDocument();
  });

  it("translates an explicit label key and keeps an unnamed resource's name", () => {
    render(<CustomMenu />);

    expect(screen.getByText(labels.alerts)).toBeInTheDocument();
    expect(
      screen.queryByText("serviceAlerts.title"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Layer")).toBeInTheDocument();
  });
});
