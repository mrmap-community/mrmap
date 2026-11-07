import {
  AdminContext,
  RaRecord,
  RecordContextProvider,
  TestMemoryRouter,
} from "react-admin";

import { render } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import BackgroundProcessAlert from "./BackgroundProcessAlert";

import "@testing-library/jest-dom/vitest";

vi.mock("notistack", () => ({
  useSnackbar: () => ({ closeSnackbar: vi.fn() }),
}));

const harvestWaitingForSchedule: RaRecord = {
  id: "7",
  processType: "harvesting",
  relatedId: "42",
  status: "pending",
  doneSteps: 3,
  totalSteps: 5,
  progress: 60,
};

// The alert body is plain text nodes separated by <br/>, so the assertions
// read the container's text rather than individual elements.
const renderAlert = (locale: "en" | "de", record: RaRecord = harvestWaitingForSchedule) =>
  render(
    <TestMemoryRouter>
      <AdminContext i18nProvider={polyglotI18nProvider(() => (locale === "de" ? de : en), locale)}>
        <RecordContextProvider value={record}>
          <BackgroundProcessAlert snackId="snack-1" />
        </RecordContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  ).container;

describe("BackgroundProcessAlert", () => {
  it("names a waiting harvest and its steps in German", () => {
    const container = renderAlert("de");

    expect(container).toHaveTextContent("Datenübernahme von 42");
    expect(container).toHaveTextContent("wartet auf den Zeitplan");
    expect(container).toHaveTextContent("3 von 5 Schritten abgeschlossen.");
  });

  it("names a waiting harvest and its steps in English, without the old typo", () => {
    const container = renderAlert("en");

    expect(container).toHaveTextContent("Harvesting of 42");
    expect(container).toHaveTextContent("waiting for schedule");
    expect(container).toHaveTextContent("3 of 5 steps done.");
    expect(container.textContent).not.toMatch(/wating/);
  });

  it.each(["en", "de"])(
    "reads a finished monitoring run in %s",
    locale => {
      const container = renderAlert(locale as "en" | "de", {
        id: "8",
        processType: "monitoring",
        status: "completed",
        progress: 100,
      });

      expect(container).toHaveTextContent("Monitoring");
      expect(container).toHaveTextContent(
        locale === "de" ? "abgeschlossen" : "completed",
      );
    },
  );
});
