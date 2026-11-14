import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import ListTemporaryMdMetadataFile from "./ListTemporaryMdMetadataFile";

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../Field/TruncatedTextField", () => ({
  default: () => null,
}));
vi.mock("../../Lists/CustomListActions", () => ({
  default: ({ isConfigureable }: { isConfigureable?: boolean }) => (
    <span>actions chooser={String(isConfigureable)}</span>
  ),
}));
vi.mock("react-admin", () => ({
  DateField: () => null,
  TextField: () => null,
}));

describe("ListTemporaryMdMetadataFile", () => {
  it("lists only the files whose import was refused, newest request first", () => {
    render(
      <ListTemporaryMdMetadataFile
        relatedResource={{ resource: "HarvestingJob", id: "1" }}
        refetchInterval={5000}
        storeKey={false}
      />,
    );
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(props?.resource).toBe("TemporaryMdMetadataFile");
    expect(props?.relatedResource).toEqual({
      resource: "HarvestingJob",
      id: "1",
    });
    expect(props?.filter).toEqual({ hasImportError: true });
    expect(props?.sort).toEqual({ field: "requestId", order: "DESC" });
    expect(props?.refetchInterval).toBe(5000);
    expect(props?.storeKey).toBe(false);
  });
  it("leaves the filter to the caller on the route of the resource itself", () => {
    // the references a registration keeps are decided by their work state and
    // not by an import error (#1263), so only the run screen is fixed to the
    // refused files; the route answers what the caller asks for (#1266)
    render(<ListTemporaryMdMetadataFile />);
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(props?.filter).toBeUndefined();
  });
  it("names the refused file by request, page, refusal and duration", () => {
    render(<ListTemporaryMdMetadataFile />);
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(
      props?.columns?.map((column) => column.props as Record<string, unknown>),
    ).toEqual([
      expect.objectContaining({
        source: "requestId",
        label: "harvestRun.failing.request",
      }),
      expect.objectContaining({
        source: "requestedUrl",
        label: "harvestRun.failing.page",
      }),
      expect.objectContaining({
        source: "importError",
        label: "harvestRun.failing.refusedWith",
      }),
      expect.objectContaining({
        source: "downloadDuration",
        label: "harvestRun.failing.downloadDuration",
      }),
    ]);
  });
  it("offers no column chooser and no export of the file contents", () => {
    // a chooser could add `mdMetadataFile` to the rows and an export would
    // read all of them - both start what this list must never start (#888)
    render(<ListTemporaryMdMetadataFile />);
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    const ActionsComponent = props?.ActionsComponent;
    expect(ActionsComponent).toBeDefined();
    render(
      ActionsComponent
        ? <ActionsComponent preferenceKey="x" />
        : <span>no actions</span>,
    );
    expect(screen.getByText("actions chooser=false")).toBeInTheDocument();
    expect(props?.rowActions).toBeDefined();
  });
});
