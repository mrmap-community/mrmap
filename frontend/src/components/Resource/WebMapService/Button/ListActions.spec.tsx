import { type ReactNode } from "react";
import { AdminContext, Button, RecordContextProvider } from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import WmsViewerButtons from "./ListActions";

vi.mock("./MapViewerButton", () => ({
  default: ({ label, children }: { label: string; children?: ReactNode }) => <Button label={label}>{children}</Button>,
}));

const renderButtons = (isSecured: boolean) => render(
  <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
    <RecordContextProvider value={{ id: "service", isSecured }}>
      <WmsViewerButtons />
    </RecordContextProvider>
  </AdminContext>,
);

describe("WMS viewer action labels", () => {
  it("explains the secured viewer separately", async () => {
    renderButtons(true);
    expect(screen.getByRole("button", { name: "Open map viewer" })).toBeInTheDocument();
    const secured = screen.getByRole("button", { name: "Open secured map viewer" });
    fireEvent.mouseOver(secured.parentElement!);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Open secured map viewer");
  });

  it("does not show a secured viewer for an unsecured service", () => {
    renderButtons(false);
    expect(screen.queryByRole("button", { name: "Open secured map viewer" })).not.toBeInTheDocument();
  });
});
