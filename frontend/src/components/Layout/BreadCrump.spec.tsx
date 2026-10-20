import { render, screen } from "@testing-library/react";
import { AdminContext, TestMemoryRouter } from "react-admin";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it } from "vitest";
import en from "../../i18n/en";
import BreadCrump from "./BreadCrump";

const renderBreadcrumb = (path: string) => render(
  <TestMemoryRouter initialEntries={[path]}>
    <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
      <BreadCrump />
    </AdminContext>
  </TestMemoryRouter>,
);

describe("BreadCrump labels", () => {
  it("uses the readable resource label", () => {
    renderBreadcrumb("/WebMapService");
    expect(screen.getByText("Web Map Services")).toBeInTheDocument();
    expect(screen.queryByText("WebMapService")).not.toBeInTheDocument();
  });

  it("keeps fallback labels for other routes and actions", () => {
    renderBreadcrumb("/custom-resource/12/show");
    expect(screen.getByRole("link", { name: "Custom Resource" })).toHaveAttribute("href", "/custom-resource");
    expect(screen.getByRole("link", { name: "#12" })).toBeInTheDocument();
    expect(screen.getByText("Show")).toBeInTheDocument();
  });
});
