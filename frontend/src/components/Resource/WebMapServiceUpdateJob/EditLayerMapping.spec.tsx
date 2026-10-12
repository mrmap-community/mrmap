import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  AdminContext,
  RecordContextProvider,
  SaveContextProvider,
  SimpleForm,
  TextInput,
  type RaRecord,
} from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { wfsUpdateConfig } from "../Generic/Update/serviceUpdateConfig";
import { EditLayerMapping } from "./EditLayerMapping";
import type { EditGuesserProps } from "../../../jsonapi/components/EditGuesser";
const { save, mapping, job, definitions, fieldsForOperation, editProps } =
  vi.hoisted(() => ({
    fieldsForOperation: vi.fn(),
    editProps: vi.fn(),
    save: vi.fn(),
    mapping: {
      id: 7,
      job: { id: 2 },
      newLayer: { id: 101 },
      oldLayer: { id: 201 },
      isConfirmed: false,
    },
    job: { id: 2, service: { id: "wms" } },
    definitions: ["job", "newLayer", "oldLayer", "isConfirmed"].map(
      (source) => ({
        component: () => null,
        props: { source },
      }),
    ),
  }));
vi.mock("../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: (params: { operationId: string }) => {
    fieldsForOperation(params);
    return params.operationId === "partial_update_FeatureTypeMapping"
      ? ["job", "newFeaturetype", "oldFeaturetype", "isConfirmed"].map(
          (source) => ({ component: () => null, props: { source } }),
        )
      : definitions;
  },
}));
vi.mock("../../../jsonapi/components/EditGuesser", () => ({
  default: ({
    simpleFormProps,
    updateFieldDefinitions,
    ...props
  }: EditGuesserProps) => {
    editProps({ ...props, updateFieldDefinitions });
    return (
      <RecordContextProvider value={mapping}>
        <SaveContextProvider
          value={{ save, saving: false, mutationMode: "pessimistic" }}
        >
          <SimpleForm {...simpleFormProps}>
            <TextInput source="oldLayer.id" label="Existing layer ID" />
            <span>
              {JSON.stringify(
                updateFieldDefinitions?.find(
                  (field) => field.props.source === "oldLayer",
                )?.props.relatedResource,
              )}
            </span>
          </SimpleForm>
        </SaveContextProvider>
      </RecordContextProvider>
    );
  },
}));
beforeEach(() => save.mockReset());
const renderEditor = () =>
  render(
    <AdminContext>
      <RecordContextProvider value={job}>
        <EditLayerMapping mapping={mapping} />
      </RecordContextProvider>
    </AdminContext>,
  );
describe("inline layer mapping decisions", () => {
  it("uses the WFS schema, relationships and confirmation transform", async () => {
    render(
      <AdminContext>
        <RecordContextProvider value={{ ...job, service: { id: "wfs" } }}>
          <EditLayerMapping
            mapping={{ id: 8, newFeaturetype: { id: 101 } }}
            config={wfsUpdateConfig}
          />
        </RecordContextProvider>
      </AdminContext>,
    );
    expect(fieldsForOperation).toHaveBeenCalledWith({
      operationId: "partial_update_FeatureTypeMapping",
    });
    const props = editProps.mock.calls.at(-1)?.[0];
    expect(props.resource).toBe("FeatureTypeMapping");
    expect(props.id).toBe(8);
    expect(
      props.updateFieldDefinitions.find(
        (field: { props: { source: string } }) =>
          field.props.source === "oldFeaturetype",
      ).props,
    ).toEqual(
      expect.objectContaining({
        relatedResource: { resource: "WebFeatureService", id: "wfs" },
        initialFilter: { hasReverseMapping: false },
        label: "wfsUpdateReview.mapExisting",
      }),
    );
    for (const source of ["job", "newFeaturetype", "isConfirmed"])
      expect(
        props.updateFieldDefinitions.find(
          (field: { props: { source: string } }) =>
            field.props.source === source,
        ).props.hidden,
      ).toBe(true);
    fireEvent.click(
      screen.getByRole("button", { name: "updateReview.confirm" }),
    );
    await waitFor(() => expect(save).toHaveBeenCalled());
    const [, options] = save.mock.calls[0];
    const values = {
      id: 8,
      newFeaturetype: { id: 101 },
      oldFeaturetype: { id: 201 },
    };
    expect(options.transform(values)).toEqual({ ...values, isConfirmed: true });
  });
  it("saves a changed relationship as pending", async () => {
    renderEditor();
    fireEvent.change(
      screen.getByRole("textbox", { name: "Existing layer ID" }),
      { target: { value: "202" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "updateReview.savePending" }),
    );
    await waitFor(() => expect(save).toHaveBeenCalled());
    const [values, options] = save.mock.calls[0] as [
      RaRecord,
      { transform: (data: RaRecord) => RaRecord },
    ];
    expect(options.transform(values)).toEqual({
      ...mapping,
      oldLayer: { id: "202" },
      isConfirmed: false,
    });
  });
  it("confirms without a field change and preserves relationships", async () => {
    renderEditor();
    fireEvent.click(
      screen.getByRole("button", { name: "updateReview.confirm" }),
    );
    await waitFor(() => expect(save).toHaveBeenCalled());
    const [values, options] = save.mock.calls[0] as [
      RaRecord,
      { transform: (data: RaRecord) => RaRecord },
    ];
    expect(options.transform(values)).toEqual({
      ...mapping,
      isConfirmed: true,
    });
    expect(
      screen.getByText('{"resource":"WebMapService","id":"wms"}'),
    ).toBeInTheDocument();
    expect(
      definitions.find((field) => field.props.source === "oldLayer")?.props,
    ).toEqual({ source: "oldLayer" });
  });
  it("does not offer rejection and disables saving an unchanged pending mapping", () => {
    renderEditor();
    expect(
      screen.getByRole("button", { name: "updateReview.savePending" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: /reject/i }),
    ).not.toBeInTheDocument();
  });
});
