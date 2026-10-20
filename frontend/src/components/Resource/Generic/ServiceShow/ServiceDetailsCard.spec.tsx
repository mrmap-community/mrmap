import { render, screen } from "@testing-library/react";
import { AdminContext, RecordContextProvider, ResourceContextProvider, SelectField, TextField } from "react-admin";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";
import en from "../../../../i18n/en";
import de from "../../../../i18n/de";
import ServiceDetailsCard from "./ServiceDetailsCard";

vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [
    ...["id", "title", "abstract"].map(source => ({ component: TextField, props: { source, label: source } })),
    { component: SelectField, props: { source: "version", choices: [{ id: 0, name: "1.3.0" }] } },
  ],
}));
vi.mock("./ServicePreviewImage", () => ({ default: () => null }));
vi.mock("./ActivateServiceButton", () => ({ default: () => null }));
vi.mock("../../WebMapService/Button/MapViewerButton", () => ({ default: () => null }));

const renderDetails = (version?: number, locale = "en") => render(
  <AdminContext i18nProvider={polyglotI18nProvider(() => locale === "de" ? de : en, locale)}>
    <ResourceContextProvider value="WebMapService">
      <RecordContextProvider value={{ id: "service", title: "Weather WMS", abstract: "Weather maps", version }}>
        <ServiceDetailsCard protocol="WMS" />
      </RecordContextProvider>
    </ResourceContextProvider>
  </AdminContext>,
);

describe("ServiceDetailsCard labels", () => {
  it("shows readable labels and hides an absent version", () => {
    renderDetails();
    for (const label of ["ID", "Title", "Abstract"]) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText("Version")).not.toBeInTheDocument();
  });

  it("keeps a version whose valid enum value is zero", () => {
    renderDetails(0);
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("1.3.0")).toBeInTheDocument();
  });

  it("translates the labels into German", () => {
    renderDetails(undefined, "de");
    expect(screen.getByText("Titel")).toBeInTheDocument();
    expect(screen.getByText("Beschreibung")).toBeInTheDocument();
  });
});
