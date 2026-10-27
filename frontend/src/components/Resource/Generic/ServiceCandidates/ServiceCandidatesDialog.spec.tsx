import type { CandidateValidation, RecordResolution } from "./useServiceCandidates";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServiceCandidatesDialog from "./ServiceCandidatesDialog";

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useResourceContext: () => "DatasetMetadataRecord",
  useRecordContext: () => ({ id: "record-1" }),
  ShowButton: ({ label, resource }: { label: string; resource: string }) => (
    <a href={`#${resource}`}>{label}</a>
  ),
}));

const state = vi.hoisted(() => ({
  resolution: undefined as RecordResolution | undefined,
  failure: undefined as { code: string } | undefined,
  validation: undefined as CandidateValidation | undefined,
  checked: undefined as string | undefined,
  openInViewer: vi.fn(),
}));

vi.mock("./useServiceCandidates", () => ({
  useServiceCandidates: () => ({
    data: state.resolution,
    isPending: false,
    error: state.failure,
  }),
  useValidateServiceCandidate: (
    _resource: string,
    _id: string,
    url: string | undefined,
  ) => {
    state.checked = url;
    return { data: state.validation, isPending: false };
  },
}));

vi.mock("./useOpenCandidateInViewer", () => ({
  useOpenCandidateInViewer: () => state.openInViewer,
}));

const WMS_URL =
  "https://maps.example.org/geoserver/ins?service=wms&version=1.3.0&request=GetCapabilities";
const WFS_URL =
  "https://maps.example.org/geoserver/ins/ows?service=wfs&version=2.0.0&request=GetCapabilities";

const candidate = (overrides: Record<string, unknown>) => ({
  url: WMS_URL,
  original_url: WMS_URL,
  kind: "capabilities",
  source: "own-distribution",
  state: "unvalidated",
  ...overrides,
}) as never;

const resolution = (overrides: Record<string, unknown>) =>
  ({
    status: "ok",
    candidates: [],
    registered_targets: [],
    ...overrides,
  }) as never;

const onClose = vi.fn();

const renderDialog = () =>
  render(
    <ServiceCandidatesDialog
      open
      onClose={onClose}
      resource="DatasetMetadataRecord"
      recordId="record-1"
    />,
  );

/** The row of an advertised endpoint, addressed by the address it shows. */
const rowOf = (path: string): HTMLElement =>
  screen.getByText(path).closest("div") as HTMLElement;

const check = (which = 0) =>
  fireEvent.click(screen.getAllByText("serviceCandidates.check")[which]);

beforeEach(() => {
  vi.clearAllMocks();
  state.resolution = undefined;
  state.failure = undefined;
  state.validation = undefined;
  state.checked = undefined;
});

describe("the candidates of a metadata record", () => {
  it("lists every advertised endpoint as unvalidated until it was asked", () => {
    state.resolution = resolution({
      candidates: [
        candidate({ service: "WMS", preferred: true }),
        candidate({
          url: WFS_URL,
          original_url: WFS_URL,
          service: "WFS",
          source: "coupled-service-record",
          derived: true,
          type_names: ["RBSN_RR"],
        }),
      ],
    }) as RecordResolution;
    renderDialog();
    expect(rowOf("maps.example.org/geoserver/ins")).toBeInTheDocument();
    expect(rowOf("maps.example.org/geoserver/ins/ows")).toBeInTheDocument();
    expect(
      screen.getAllByText("serviceCandidates.state.unvalidated"),
    ).toHaveLength(2);
    expect(screen.getByText("serviceCandidates.preferred")).toBeInTheDocument();
    expect(screen.getByText("serviceCandidates.derived")).toBeInTheDocument();
    expect(screen.getByText("RBSN_RR")).toBeInTheDocument();
    // discovery promises that no endpoint was asked
    expect(screen.getAllByText("serviceCandidates.check")).toHaveLength(2);
  });

  it("asks only the endpoint of the candidate which was checked", () => {
    state.resolution = resolution({
      candidates: [
        candidate({ service: "WMS" }),
        candidate({ url: WFS_URL, original_url: WFS_URL, service: "WFS" }),
      ],
    }) as RecordResolution;
    renderDialog();
    check();
    expect(state.checked).toBe(WMS_URL);
    check(1);
    expect(state.checked).toBe(WFS_URL);
  });

  it("separates the hints the endpoint confirmed from the ones it did not", () => {
    state.resolution = resolution({
      candidates: [candidate({ service: "WFS", type_names: ["RBSN_RR", "RBSN_FF"] })],
    }) as RecordResolution;
    state.validation = {
      state: "ambiguous",
      detail: "unresolved-hints",
      matched_names: ["RBSN_RR"],
      unresolved_hints: ["RBSN_FF"],
    } as CandidateValidation;
    renderDialog();
    check();
    expect(screen.getByText("RBSN_RR")).toBeInTheDocument();
    expect(screen.getByText("RBSN_FF")).toBeInTheDocument();
    // the answer of the endpoint replaces the chip of the unvalidated row
    expect(
      screen.queryByText("serviceCandidates.state.unvalidated"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.state.ambiguous"),
    ).toBeInTheDocument();
    expect(screen.getByText("unresolved-hints")).toBeInTheDocument();
    // an ambiguous hint stays a decision of the user, so nothing is added
    expect(screen.getByText("serviceCandidates.openInMap").closest("button")).toHaveTextContent(
      "serviceCandidates.openInMap",
    );
  });

  it("names a supported answer and keeps an unsupported one as a reason", () => {
    state.resolution = resolution({
      candidates: [candidate({ service: "WMS" })],
    }) as RecordResolution;
    state.validation = {
      state: "unsupported",
      detail: "unsupported-service",
    } as CandidateValidation;
    renderDialog();
    check();
    expect(
      screen.getByText("serviceCandidates.state.unsupported"),
    ).toBeInTheDocument();
    expect(screen.getByText("unsupported-service")).toBeInTheDocument();
  });

  it("states what the record answers instead of an empty list", () => {
    state.resolution = resolution({
      status: "missing",
      candidates: [],
      registered_targets: [],
    }) as RecordResolution;
    renderDialog();
    expect(
      screen.getByText("serviceCandidates.status.missing"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("serviceCandidates.none"),
    ).not.toBeInTheDocument();
  });

  it("keeps registered resources apart from the advertised endpoints", () => {
    state.resolution = resolution({
      registered_targets: [{ resource_type: "wms", id: 12, name: "Niederschlag" }],
    }) as RecordResolution;
    renderDialog();
    expect(
      screen.getByText("serviceCandidates.registeredTitle"),
    ).toBeInTheDocument();
    expect(screen.getByText("Niederschlag")).toBeInTheDocument();
    expect(screen.getByText("ra.action.show")).toHaveAttribute(
      "href",
      "#WebMapService",
    );
    // nothing is advertised, so there is nothing to ask or to add
    expect(
      screen.queryByText("serviceCandidates.check"),
    ).not.toBeInTheDocument();
  });

  it("adds the selected endpoint to the map instead of registering it", () => {
    state.resolution = resolution({
      candidates: [candidate({ service: "WMS" })],
    }) as RecordResolution;
    renderDialog();
    const addButton = screen
      .getByText("serviceCandidates.openInMap")
      .closest("button") as HTMLButtonElement;
    // the handoff needs a selection, an empty choice cannot add anything
    expect(addButton).toBeDisabled();
    fireEvent.click(screen.getByText("maps.example.org/geoserver/ins"));
    expect(addButton).toBeEnabled();
    fireEvent.click(addButton);
    expect(state.openInViewer).toHaveBeenCalledWith(WMS_URL);
    expect(onClose).toHaveBeenCalled();
  });

  it("tells a refused record by the reason the api answered", () => {
    state.failure = { code: "denied" };
    renderDialog();
    expect(screen.getByText("serviceCandidates.error.denied")).toBeInTheDocument();
  });
});
