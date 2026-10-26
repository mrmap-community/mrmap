import {
  AdminContext,
  ResourceContextProvider,
  testDataProvider,
} from "react-admin";
import { FormProvider, useForm } from "react-hook-form";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../i18n/en";
import CronInput from "./CronInput";

// the dialog with its portal and form needs more than the default timeout
vi.setConfig({ testTimeout: 20000 });

const Harness = () => {
  const form = useForm({ defaultValues: { cron: "* * * * *" } });
  return (
    <FormProvider {...form}>
      <CronInput source="cron" />
    </FormProvider>
  );
};

const renderInput = () =>
  render(
    <AdminContext
      dataProvider={testDataProvider()}
     
      i18nProvider={polyglotI18nProvider(() => en, "en")}
    >
      <ResourceContextProvider value="PeriodicTask">
        <Harness />
      </ResourceContextProvider>
    </AdminContext>,
  );

describe("CronInput", () => {
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
    renderInput();
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
});
