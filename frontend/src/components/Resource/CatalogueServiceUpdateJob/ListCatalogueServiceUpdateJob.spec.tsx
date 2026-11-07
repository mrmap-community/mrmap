import type { ReactNode } from "react";

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ListWithDialogs from "../../../jsonapi/components/ListWithDialogs";
import CustomListActions from "../../Lists/CustomListActions";
import ListCatalogueServiceUpdateJob from "./ListCatalogueServiceUpdateJob";

vi.mock("../../../jsonapi/components/ListWithDialogs", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../Lists/CustomListActions", () => ({
  default: vi.fn(() => null),
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useRecordContext: () => undefined,
  DateField: () => null,
  FunctionField: () => null,
  TextField: () => null,
}));

const listProps = () =>
  vi.mocked(ListWithDialogs).mock.calls.at(-1)?.[0].listGuesserProps;

describe("ListCatalogueServiceUpdateJob", () => {
  it("lists the jobs newest first and opens the job it shows a row of", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const props = listProps();
    expect(props?.resource).toBe("CatalogueServiceUpdateJob");
    expect(props?.perPage).toBe(25);
    expect(props?.sort).toEqual({ field: "dateCreated", order: "DESC" });
    expect(props?.dataGridProps?.rowClick).toBe("show");
  });

  it("keeps the column chooser off: every column is a question about a job", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const Actions = listProps()?.ActionsComponent;
    expect(Actions).toBeDefined();
    if (Actions) render(<Actions />);
    expect(vi.mocked(CustomListActions).mock.calls.at(-1)?.[0]).toMatchObject({
      isConfigureable: false,
    });
  });

  it("names the catalogue as a reference and not as an id", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const service = listProps()?.columns?.find(
      (element) => element.key === "service",
    );
    expect(
      (service?.props as unknown as { reference: string }).reference,
    ).toBe("CatalogueService");
  });

  it("renders the chip which names the state in the status column", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const columns = listProps()?.columns ?? [];
    const status = columns.find((element) => element.key === "status");
    const renderCell = (
      status?.props as unknown as { render: () => ReactNode }
    ).render;
    const { getByText } = render(<>{renderCell()}</>);
    // no record on hand: the chip stays silent rather than guessing a state
    expect(getByText("—")).toBeInTheDocument();
  });
});
