import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, type RenderResult } from "@testing-library/react";
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

/** the cell of the named column of a job row */
const renderColumn = (key: string, record: RaRecord): RenderResult => {
  const columns = listProps()?.columns ?? [];
  const column = columns.find((element) => element.key === key);
  const renderCell = (
    column?.props as unknown as { render: (record: RaRecord) => ReactNode }
  ).render;
  return render(<>{renderCell(record)}</>);
};

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

  it("says what a job which waits for a decision waits for", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const { getByText } = renderColumn("waitsFor", {
      id: 7,
      statusCode: 2,
      status: "Review required",
    });
    expect(
      getByText("resources.CatalogueServiceUpdateJob.waitsFor.reviewRequired"),
    ).toBeInTheDocument();
  });

  it("answers nothing to wait for at a job which ended", () => {
    render(<ListCatalogueServiceUpdateJob />);
    const { getByText } = renderColumn("waitsFor", {
      id: 8,
      statusCode: 5,
      status: "Updated",
      doneAt: "2026-11-01T00:00:00Z",
    });
    expect(getByText("—")).toBeInTheDocument();
  });
});
