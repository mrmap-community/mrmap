import {
  AdminContext,
  ResourceContextProvider,
  testDataProvider,
} from "react-admin";
import { FormProvider, useForm } from "react-hook-form";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import de from "../../i18n/de";
import en from "../../i18n/en";
import CronInput from "./CronInput";

// the dialog with its portal and form needs more than the default timeout
vi.setConfig({ testTimeout: 20000 });

const Harness = ({ initialValue }: { initialValue?: string }) => {
  const form = useForm({ defaultValues: { cron: initialValue } });
  return (
    <FormProvider {...form}>
      <CronInput source="cron" />
    </FormProvider>
  );
};

const renderInput = (initialValue?: string, locale: "en" | "de" = "en") =>
  render(
    <AdminContext
      dataProvider={testDataProvider()}

      i18nProvider={polyglotI18nProvider(() => (locale === "de" ? de : en), locale)}
    >
      <ResourceContextProvider value="PeriodicTask">
        <Harness initialValue={initialValue} />
      </ResourceContextProvider>
    </AdminContext>,
  );

const selectOptions = async (label: string, ...options: string[]) => {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  const listbox = await screen.findByRole("listbox");
  for (const option of options)
    fireEvent.click(
      // numeric options are substrings of each other, so match the full name
      within(listbox).getByRole("option", {
        name: (accessibleName) => accessibleName === option,
      }),
    );
  fireEvent.keyDown(listbox, { key: "Escape" });
  await waitFor(() =>
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument(),
  );
};

describe("CronInput", () => {
  it("defaults new schedules to minute zero when selecting 11:00 and 23:00", async () => {
    renderInput();
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    await selectOptions("Hour", "23", "11");
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "0 11,23 * * *",
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("textbox")).toHaveValue("0 11,23 * * *");
  });

  it("loads saved selections and preserves the timezone when correcting the minute", async () => {
    renderInput("* 11,23 * * * Europe/Berlin");
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    expect(screen.getByRole("combobox", { name: "Hour" })).toHaveTextContent(
      "11, 23",
    );
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "* 11,23 * * * Europe/Berlin",
    );
    await selectOptions("Minute", "0");
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "0 11,23 * * * Europe/Berlin",
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("textbox")).toHaveValue(
      "0 11,23 * * * Europe/Berlin",
    );
  });

  it("lets an explicit wildcard replace concrete minutes and vice versa", async () => {
    renderInput("0 11,23 * * * Europe/Berlin");
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    await selectOptions("Minute", "* (every)");
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "* 11,23 * * * Europe/Berlin",
    );
    await selectOptions("Minute", "15");
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "15 11,23 * * * Europe/Berlin",
    );
  });

  it.each(["* 11,23 * * * Europe/Berlin", "*/5 11,23 * * 1-5 Europe/Berlin"])(
    "preserves saved cron %s when applying without changes",
    async (cron) => {
      renderInput(cron);
      fireEvent.click(screen.getByRole("textbox"));
      await screen.findByRole("dialog");
      fireEvent.click(screen.getByRole("button", { name: "Apply" }));
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      expect(screen.getByRole("textbox")).toHaveValue(cron);
    },
  );

  it("discards picker edits when cancelling and reopening", async () => {
    renderInput("0 11 * * * Europe/Berlin");
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    await selectOptions("Hour", "23");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    expect(screen.getByRole("combobox", { name: "Hour" })).toHaveTextContent(
      "11",
    );
    expect(screen.getByLabelText("Preview / manual edit")).toHaveValue(
      "0 11 * * * Europe/Berlin",
    );
  });

  it("opens the shared dialog and applies the preview to the form field", async () => {
    renderInput();
    fireEvent.click(screen.getByRole("textbox"));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName("Edit Cron Expression");
    fireEvent.change(screen.getByLabelText("Preview / manual edit"), {
      target: { value: "0 12 * * 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
      "0 12 * * 1",
    );
  });

  it("dismisses the dialog through Cancel without applying", async () => {
    renderInput("* * * * *");
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    fireEvent.change(screen.getByLabelText("Preview / manual edit"), {
      target: { value: "0 12 * * 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
      "* * * * *",
    );
  });

  it("dismisses through the labelled close control", async () => {
    renderInput();
    fireEvent.click(screen.getByRole("textbox"));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("renders the whole editor in German when the user works in German", async () => {
    renderInput("0 11 * * * Europe/Berlin", "de");
    fireEvent.click(screen.getByRole("textbox"));
    const dialog = await screen.findByRole("dialog");

    expect(dialog).toHaveAccessibleName("Cron-Ausdruck bearbeiten");
    expect(
      within(dialog).getByRole("combobox", { name: "Minute" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("combobox", { name: "Stunde" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("combobox", { name: "Monatstag" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("combobox", { name: "Monat" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("combobox", { name: "Wochentag (0=So)" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Abbrechen" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Anwenden" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByLabelText("Vorschau / manuelle Eingabe"),
    ).toBeInTheDocument();
    // the editor speaks one language at a time
    expect(
      within(dialog).queryByRole("combobox", { name: "Hour" }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).queryByText("Day of Month"),
    ).not.toBeInTheDocument();
  });
});
