import {
  AdminContext,
  BooleanInput,
  ResourceDefinitionContextProvider,
  TextInput,
  memoryStore,
  required,
  testDataProvider,
} from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../i18n/en";
import SchemaAutocompleteInput from "../../../jsonapi/components/SchemaAutocompleteInput";
import { useFieldsForOperation } from "../../../jsonapi/hooks/useFieldsForOperation";
import BulkCreateHarvestingSchedulesButton from "./BulkCreateHarvestingSchedulesButton";

const state = vi.hoisted(() => ({
  selectedIds: ["csw-1", "csw-off-page"],
  identity: { id: "user-1" } as { id: string } | undefined,
  unselect: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("react-admin", async importOriginal => ({
  ...await importOriginal<typeof import("react-admin")>(),
  useListContext: () => ({ selectedIds: state.selectedIds, data: [{ id: "csw-1", periodicHarvestingJobs: [{ id: "existing" }] }] }),
  useGetIdentity: () => ({ data: state.identity }),
  useUnselect: () => state.unselect,
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
}));
vi.mock("../../../jsonapi/hooks/useFieldsForOperation", () => ({ useFieldsForOperation: vi.fn() }));

const label = "Add harvesting schedule to selected CSWs";
const renderButton = (create = vi.fn().mockResolvedValue({ data: { id: "schedule-1" } }), hasCreate = true) => {
  render(
    <AdminContext
      store={memoryStore()}
      i18nProvider={polyglotI18nProvider(() => en, "en")}
      dataProvider={testDataProvider({ create })}
    >
      <ResourceDefinitionContextProvider definitions={{
        PeriodicHarvestingJob: { name: "PeriodicHarvestingJob", hasCreate },
      }}>
        <BulkCreateHarvestingSchedulesButton />
      </ResourceDefinitionContextProvider>
    </AdminContext>,
  );
  return create;
};
const openDialog = async () => {
  fireEvent.click(screen.getByRole("button", { name: label }));
  return await screen.findByRole("dialog", { name: label });
};

beforeEach(() => {
  vi.clearAllMocks();
  state.selectedIds = ["csw-1", "csw-off-page"];
  state.identity = { id: "user-1" };
  vi.mocked(useFieldsForOperation).mockReturnValue([
    { component: SchemaAutocompleteInput, props: { source: "catalogue", reference: "CatalogueService", label: "Catalogue", validate: [required()] } },
    { component: TextInput, props: { source: "scheduling", label: "Schedule", validate: [required()] } },
    { component: BooleanInput, props: { source: "enabled", label: "Enabled", defaultValue: true } },
  ]);
});

describe("bulk harvesting schedules", () => {
  it("uses one schema form for every selected ID, including existing schedules and other pages", async () => {
    const create = renderButton();
    const dialog = await openDialog();
    expect(within(dialog).getByText(/each of 2 selected catalogues/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Catalogue")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("textbox", { name: "Schedule" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Preview / manual edit" }), {
      target: { value: "0 2 * * *" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit Cron Expression" })).not.toBeInTheDocument());
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    for (const id of state.selectedIds) {
      expect(create).toHaveBeenCalledWith("PeriodicHarvestingJob", expect.objectContaining({
        data: { scheduling: "0 2 * * *", enabled: true, catalogue: { id } },
      }));
    }
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(state.unselect).toHaveBeenCalledWith(state.selectedIds);
    expect(state.notify).toHaveBeenCalledWith("harvestingSchedules.bulkResult", {
      type: "success", messageArgs: { created: 2, failed: 0 },
    });
    expect(state.refresh).toHaveBeenCalledOnce();
  });

  it("keeps failures selected and retries them without duplicating successful schedules", async () => {
    const create = vi.fn()
      .mockResolvedValueOnce({ data: { id: "schedule-1" } })
      .mockRejectedValueOnce(new Error("Forbidden"))
      .mockResolvedValueOnce({ data: { id: "schedule-2" } });
    renderButton(create);
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("csw-off-page");
    expect(state.unselect).toHaveBeenCalledWith(["csw-1"]);
    expect(state.notify).toHaveBeenCalledWith("harvestingSchedules.bulkResult", {
      type: "warning", messageArgs: { created: 1, failed: 1 },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: label }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(create).toHaveBeenCalledTimes(3);
    expect(create.mock.calls[2][1].data.catalogue).toEqual({ id: "csw-off-page" });
    expect(state.unselect).toHaveBeenLastCalledWith(["csw-off-page"]);
  });

  it("prevents repeat submissions and dismissal while a batch is pending", async () => {
    state.selectedIds = ["csw-1"];
    let finish: (result: { data: { id: string } }) => void = () => undefined;
    const create = vi.fn(() => new Promise(resolve => { finish = resolve; }));
    renderButton(create);
    const dialog = await openDialog();
    const submit = within(dialog).getByRole("button", { name: label });
    fireEvent.click(submit);
    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(submit).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(dialog).toBeInTheDocument();
    finish({ data: { id: "schedule-1" } });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("cancels without creating schedules", async () => {
    const create = renderButton();
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(create).not.toHaveBeenCalled();
  });

  it.each(["anonymous", "unavailable", "missing schema"])("hides the action when %s", reason => {
    if (reason === "anonymous") state.identity = undefined;
    if (reason === "missing schema") vi.mocked(useFieldsForOperation).mockReturnValue([]);
    renderButton(undefined, reason !== "unavailable");
    expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
  });

  it("requires a selection", () => {
    state.selectedIds = [];
    renderButton();
    expect(screen.getByRole("button", { name: label })).toBeDisabled();
  });
});
