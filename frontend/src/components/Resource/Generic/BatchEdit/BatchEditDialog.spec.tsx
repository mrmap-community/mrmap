import type { FieldDefinition } from "../../../../jsonapi/utils";
import type { OpenAPIV3 } from "openapi-client-axios";

import {
  AdminContext,
  type Identifier,
  type RaRecord,
  ResourceDefinitionContextProvider,
  testDataProvider,
  TextInput,
  useInput,
} from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import BatchEditButton from "./BatchEditButton";
import { BATCH_EDIT_MAX_RECORDS } from "./BatchEditDialog";

interface GetManyParams {
  ids: Identifier[];
  meta?: { jsonApiParams?: Record<string, string> };
}

interface UpdateParams {
  id: Identifier;
  data: Record<string, unknown>;
  previousData: RaRecord;
}

const state = vi.hoisted(() => ({
  hasPatch: true,
  selectedIds: ["r1", "r2", "r3"] as string[],
  records: [] as RaRecord[],
  failGetMany: false,
  schema: undefined as OpenAPIV3.NonArraySchemaObject | undefined,
  unselect: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  update: vi.fn(),
  recordMeta: undefined as Record<string, string> | undefined,
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({
    api: {
      getOperation: (operationId: string) =>
        state.hasPatch &&
        operationId === "partial_update_ApplicationMetadataRecord"
          ? {}
          : undefined,
    },
  }),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: vi.fn(),
}));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({
  default: (operationId?: string) =>
    operationId?.startsWith("list_")
      ? { includeAbleResources: ["metadataContact"] }
      : { schema: state.schema },
}));
vi.mock("../../../../jsonapi/hooks/useSchemaRecordRepresentation", () => ({
  default: () => (record: RaRecord) => (record.name ?? String(record.id)) as string,
}));
vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  useListContext: () => ({
    resource: "ApplicationMetadataRecord",
    selectedIds: state.selectedIds,
  }),
  useUnselect: () => state.unselect,
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
}));

/** A stand-in for the schema-driven reference input: a batch always sets one
 *  related record, and the form value shape ({id}) is what the write path of
 *  the ordinary edit would produce - only the input is simplified here. */
const SetContactInput = () => {
  const { field } = useInput({ source: "metadataContact" });
  return (
    <button type="button" onClick={() => field.onChange({ id: "contact-1" })}>
      set contact
    </button>
  );
};

const patchSchema = {
  properties: {
    attributes: {
      properties: {
        abstract: { type: "string", "x-iso-path": "identification.abstract" },
        title: { type: "string" },
      },
    },
    relationships: {
      properties: {
        metadataContact: {
          "x-iso-path": "contact.pointOfContact",
          properties: {
            data: { type: "object", properties: { type: { enum: ["Contact"] } } },
          },
        },
      },
    },
  },
} as never;

const definitions: FieldDefinition[] = [
  { component: TextInput, props: { source: "abstract", label: "Abstract" } },
  { component: TextInput, props: { source: "title", label: "Title" } },
  {
    component: SetContactInput,
    props: { source: "metadataContact", label: "Metadata contact" },
  },
];

const record = (id: string, overrides: Partial<RaRecord> = {}): RaRecord => ({
  id,
  title: `Record ${id}`,
  allowedActions: ["view", "change"],
  abstract: "old abstract",
  ...overrides,
});

const renderButton = () => {
  const dataProvider = testDataProvider({
    getMany: ((resource: string, params: GetManyParams) => {
      if (state.failGetMany) return Promise.reject(new Error("boom"));
      if (resource === "ApplicationMetadataRecord") {
        state.recordMeta = params.meta?.jsonApiParams;
        const wanted = new Set(params.ids.map(String));
        return Promise.resolve({
          data: state.records.filter((item) => wanted.has(String(item.id))),
        });
      }
      return Promise.resolve({
        data: params.ids.map((id) => ({ id, name: "Alice" })),
      });
    }) as never,
    update: ((resource: string, params: UpdateParams) =>
      state.update(resource, params).then(() => ({
        data: record(String(params.id)),
      }))) as never,
  });
  render(
    <AdminContext
      dataProvider={dataProvider}
      i18nProvider={polyglotI18nProvider(() => en, "en")}
    >
      <ResourceDefinitionContextProvider
        definitions={{
          ApplicationMetadataRecord: { name: "ApplicationMetadataRecord" },
        }}
      >
        <BatchEditButton />
      </ResourceDefinitionContextProvider>
    </AdminContext>,
  );
  return state.update;
};

const openDialog = async () => {
  fireEvent.click(screen.getByRole("button", { name: "Batch edit" }));
  return screen.findByRole("dialog", {
    name: `Batch edit one element of ${state.selectedIds.length} selected records`,
  });
};

const chooseElement = async (label: string) => {
  fireEvent.mouseDown(screen.getByRole("combobox"));
  fireEvent.click(await screen.findByRole("option", { name: label }));
};

const waitForPreviewReady = async () => {
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Preview" })).toBeEnabled(),
  );
};

const openPreview = async (value: string) => {
  await waitForPreviewReady();
  fireEvent.change(await screen.findByRole("textbox", { name: "Abstract" }), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  // validation is async - wait until the preview table is actually there
  await screen.findByText("Current value");
};

beforeEach(() => {
  vi.clearAllMocks();
  state.hasPatch = true;
  state.selectedIds = ["r1", "r2", "r3"];
  state.records = [
    record("r1"),
    record("r2", { allowedActions: [] }),
    record("r3", { abstract: "new abstract" }),
  ];
  state.failGetMany = false;
  state.recordMeta = undefined;
  state.update.mockReset();
  state.update.mockResolvedValue(undefined);
  state.schema = patchSchema;
  vi.mocked(useFieldsForOperation).mockReturnValue(definitions);
});

describe("batch edit", () => {
  it("is only offered when the api answers a PATCH for the resource", () => {
    state.hasPatch = false;
    renderButton();
    expect(
      screen.queryByRole("button", { name: "Batch edit" }),
    ).not.toBeInTheDocument();
  });

  it("previews the change and writes only editable, changed records - one PATCH each", async () => {
    const update = renderButton();
    const dialog = await openDialog();

    await chooseElement("Abstract");
    await waitForPreviewReady();
    expect(dialog).toHaveTextContent("Mapped to identification.abstract");

    await openPreview("new abstract");
    expect(within(dialog).getByText("not editable")).toBeInTheDocument();
    expect(within(dialog).getByText("unchanged")).toBeInTheDocument();
    expect(state.recordMeta).toMatchObject({
      "fields[ApplicationMetadataRecord]": "id,title,allowed_actions,abstract",
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Apply to 1 record" }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledWith("ApplicationMetadataRecord", {
      id: "r1",
      data: { abstract: "new abstract" },
      previousData: expect.objectContaining({ id: "r1" }),
    });
    expect(await within(dialog).findByText("Saved")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Skipped")).toHaveLength(2);
    expect(state.notify).toHaveBeenCalledWith("batchEdit.result", {
      type: "success",
      messageArgs: { applied: 1, rejected: 0 },
    });
    expect(state.unselect).toHaveBeenCalledWith(["r1", "r2", "r3"]);
    expect(state.refresh).toHaveBeenCalledOnce();
  });

  it("lists the validation errors of a refused record and keeps it selected", async () => {
    state.update.mockRejectedValueOnce(
      Object.assign(new Error("Request failed with status code 400"), {
        isAxiosError: true,
        response: {
          status: 400,
          data: { errors: [{ detail: "abstract: value too short" }] },
        },
      }),
    );
    const update = renderButton();
    const dialog = await openDialog();
    await chooseElement("Abstract");
    await openPreview("x");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Apply to 2 records" }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(
      await within(dialog).findByText("abstract: value too short"),
    ).toBeInTheDocument();
    expect(await within(dialog).findByText("Rejected")).toBeInTheDocument();
    expect(await within(dialog).findByText("Saved")).toBeInTheDocument();
    expect(state.notify).toHaveBeenCalledWith("batchEdit.result", {
      type: "warning",
      messageArgs: { applied: 1, rejected: 1 },
    });
    // the refused record stays selected for a narrowed retry
    expect(state.unselect).toHaveBeenCalledWith(["r2", "r3"]);
  });

  it("names related records by representation and writes the relationship value", async () => {
    const update = renderButton();
    const dialog = await openDialog();
    await chooseElement("Metadata contact");
    await waitForPreviewReady();

    fireEvent.click(screen.getByRole("button", { name: "set contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText("Current value");
    expect(state.recordMeta).toMatchObject({
      "fields[ApplicationMetadataRecord]":
        "id,title,allowed_actions,metadata_contact",
      include: "metadata_contact",
      "fields[Contact]": "id,string_representation",
    });
    // every row carries the same new value
    expect(await within(dialog).findAllByText("Alice")).toHaveLength(3);
    expect(within(dialog).getAllByText("no value")).toHaveLength(3);

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Apply to 2 records" }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    for (const id of ["r1", "r3"]) {
      expect(update).toHaveBeenCalledWith("ApplicationMetadataRecord", {
        id,
        data: { metadataContact: { id: "contact-1" } },
        previousData: expect.objectContaining({ id }),
      });
    }
  });

  it("refuses a selection beyond the cap and guides to filter further", async () => {
    state.selectedIds = Array.from(
      { length: BATCH_EDIT_MAX_RECORDS + 1 },
      (_, i) => `r${i + 1}`,
    );
    state.records = state.selectedIds.map((id) => record(id));
    const update = renderButton();
    const dialog = await openDialog();
    await chooseElement("Abstract");
    await openPreview("new abstract");

    expect(
      within(dialog).getByText(
        new RegExp(`more than ${BATCH_EDIT_MAX_RECORDS} records`),
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", {
        name: `Apply to ${BATCH_EDIT_MAX_RECORDS + 1} records`,
      }),
    ).toBeDisabled();
    expect(update).not.toHaveBeenCalled();
  });

  it("marks selected records that disappeared as untouched", async () => {
    state.records = state.records.slice(0, 2);
    const update = renderButton();
    const dialog = await openDialog();
    await chooseElement("Abstract");
    await openPreview("new abstract");

    expect(
      await within(dialog).findByText(
        /were not found and are left untouched/,
      ),
    ).toBeInTheDocument();
    // the third record is absent from the rows, so only r1 is written
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Apply to 1 record" }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0][1].id).toBe("r1");
  });

  it("blocks the preview while the current values cannot be loaded", async () => {
    state.failGetMany = true;
    const update = renderButton();
    const dialog = await openDialog();
    await chooseElement("Abstract");

    expect(
      await within(dialog).findByText(/could not be loaded/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Preview" }),
    ).toBeDisabled();
    expect(update).not.toHaveBeenCalled();
  });
});
