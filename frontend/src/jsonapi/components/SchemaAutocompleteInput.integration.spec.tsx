import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  AdminContext,
  SimpleForm,
  useRefresh,
  testDataProvider,
  type RaRecord,
} from "react-admin";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import SchemaAutocompleteInput from "./SchemaAutocompleteInput";

vi.mock("../hooks/useResourceSchema", () => ({
  default: () => ({
    schema: { properties: { attributes: { properties: {} } } },
  }),
}));

const RefreshChoices = () => {
  const refresh = useRefresh();
  return <button onClick={refresh}>Refresh choices</button>;
};

it("selects, clears and refreshes a filter without producing an empty option", async () => {
  const records: RaRecord[] = [{ id: 20 }];
  render(
    <MemoryRouter>
      <AdminContext
        dataProvider={testDataProvider({
          getList: async <RecordType extends RaRecord>() => ({
            data: records as RecordType[],
            total: 1,
          }),
          getMany: async <RecordType extends RaRecord>() => ({
            data: records as RecordType[],
          }),
        })}
      >
        <RefreshChoices />
        <SimpleForm toolbar={false} defaultValues={{ operation: "" }}>
          <SchemaAutocompleteInput
            reference="WebMapServiceOperation"
            source="operation"
            label="Operation"
            parse={undefined}
            format={undefined}
          />
        </SimpleForm>
      </AdminContext>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "ra.action.open" }));
  fireEvent.click(await screen.findByRole("option", { name: "20" }));
  expect(screen.getByRole("combobox", { name: "Operation" })).toHaveValue("20");
  fireEvent.click(
    screen.getByRole("button", { name: "ra.action.clear_input_value" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Refresh choices" }));
  await waitFor(() =>
    expect(screen.getByRole("combobox", { name: "Operation" })).toHaveValue(""),
  );
  fireEvent.click(screen.getByRole("button", { name: "ra.action.open" }));
  expect(await screen.findByRole("option", { name: "20" })).toBeInTheDocument();
});
