import { useTranslate } from "react-admin";

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
    // #833: the public list - a granted entry an anonymous visitor keeps.
    WebMapService: menuEntry("WebMapService", "WMS", 10),
    // The Accounts group #836 gates: an administration user opens it, a
    // plain user sees neither the entries nor the group.
    User: menuEntry("User", "Accounts", 10),
    Organization: menuEntry("Organization", "Accounts", 20),
  };
});

/** Which checks the mocked react-admin access hooks are to answer how. */
const access = vi.hoisted(() => ({ denied: [] as string[], pending: false, session: true }));

// The menu renders its entries through these react-admin pieces; the test
// asserts the text the menu hands them, so they are replaced by their label.
vi.mock("react-admin", () => ({
  useAuthState: () => ({ authenticated: access.session }),
  DashboardMenuItem: () => null,
  MenuItemLink: ({ primaryText }: { primaryText: string }) => (
    <span>{primaryText}</span>
  ),
  useCanAccessResources: ({ resources: names }: { resources: string[] }) =>
    access.pending
      ? { canAccess: undefined, isPending: true }
      : {
          canAccess: Object.fromEntries(
            names.map(name => [name, !access.denied.includes(name)])
          ),
          isPending: false,
        },
  useResourceDefinitions: () => resources,
  useSidebarState: () => [true, vi.fn()],
  useTranslate: vi.fn(),
}));

describe.each([
  {
    locale: "de",
    catalogue: "Katalogdienste",
    harvesting: "Datenübernahmen",
    updateJobs: "Aktualisierungsläufe der Katalogdienste",
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

/**
 * #836: the menu asks react-admin's access hook per group, so a user whose
 * snapshot does not carry administration loses the Accounts entries - and
 * with them the empty group - while a granted one keeps everything.
 */
describe("menu entries gated by canAccess", () => {
  beforeEach(async () => {
    await i18nProvider.changeLocale("en");
    vi.mocked(useTranslate).mockReturnValue(i18nProvider.translate);
    access.denied = [];
    access.pending = false;
    access.session = true;
  });

  afterEach(() => {
    access.denied = [];
    access.pending = false;
    access.session = true;
  });

  it("hides the denied entries and the group they would empty", () => {
    access.denied = ["User", "Organization"];
    render(<CustomMenu />);

    expect(screen.queryByText("User")).not.toBeInTheDocument();
    expect(screen.queryByText("Organization")).not.toBeInTheDocument();
    expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
    // granted groups are untouched
    expect(screen.getByText("Layer")).toBeInTheDocument();
  });

  it("keeps the group as long as one entry is granted", () => {
    access.denied = ["User"];
    render(<CustomMenu />);

    expect(screen.getByText("Organization")).toBeInTheDocument();
    expect(screen.getByText("Accounts")).toBeInTheDocument();
    expect(screen.queryByText("User")).not.toBeInTheDocument();
  });

  it("shows every entry once all are granted", () => {
    render(<CustomMenu />);

    expect(screen.getByText("User")).toBeInTheDocument();
    expect(screen.getByText("Organization")).toBeInTheDocument();
    expect(screen.getByText("Accounts")).toBeInTheDocument();
  });

  it("renders nothing of a group while its access check is still running", () => {
    access.pending = true;
    render(<CustomMenu />);

    expect(screen.queryByText("Layer")).not.toBeInTheDocument();
    expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
  });

  it("offers an anonymous visitor only the granted public list, not the session screens", () => {
    // #833: without a session only what `canAccess` keeps (the published
    // kinds of service) is offered; dashboard, explorer and viewer belong to
    // a session and are not rendered for this visitor
    access.session = false;
    access.denied = [
      "CatalogueService", "HarvestingJob", "CatalogueServiceUpdateJob",
      "ServiceAlert", "Layer", "User", "Organization",
    ];
    render(<CustomMenu />);

    expect(screen.getByText("WebMapService")).toBeInTheDocument();
    expect(screen.queryByText("Layer")).not.toBeInTheDocument();
    expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
    expect(screen.queryByText("MapViewer")).not.toBeInTheDocument();
    expect(screen.queryByText("Service explorer")).not.toBeInTheDocument();
  });
});
