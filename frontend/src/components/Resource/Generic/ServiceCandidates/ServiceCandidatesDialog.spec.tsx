import type {
  CandidateValidation,
  RecordResolution,
} from "./useServiceCandidates";

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
  registeredTargetResource: {
    wms: "WebMapService",
    wfs: "WebFeatureService",
    csw: "CatalogueService",
    layer: "Layer",
    feature_type: "FeatureType",
  },
}));

// the registration step answers its own spec; here only the switching of the
// dialog is of interest
vi.mock("./CandidateRegistration", () => ({
  CandidateRegistrationButton: ({
    candidate,
    answer,
    onRegister,
  }: {
    candidate?: { url: string };
    answer?: unknown;
    onRegister: (target: unknown) => void;
  }) =>
    !candidate ? null : (
      <button
        onClick={() =>
          onRegister({ resource: "WebMapService", candidate, answer })
        }
      >
        {`Register ${candidate.url}`}
      </button>
    ),
  CandidateRegistrationForm: ({
    target,
  }: {
    target: { candidate: { url: string }; resource: string };
  }) => <div>{`Form of ${target.resource} for ${target.candidate.url}`}</div>,
}));

vi.mock("./useOpenCandidateInViewer", () => ({
  useOpenCandidateInViewer: () => state.openInViewer,
}));

const WMS_URL =
  "https://maps.example.org/geoserver/ins?service=wms&version=1.3.0&request=GetCapabilities";
const WFS_URL =
  "https://maps.example.org/geoserver/ins/ows?service=wfs&version=2.0.0&request=GetCapabilities";

const candidate = (overrides: Record<string, unknown>) =>
  ({
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
    // protocol and origin are told per candidate, not only by their order
    expect(
      screen.getByText("serviceCandidates.source.own-distribution"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.source.coupled-service-record"),
    ).toBeInTheDocument();
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
      candidates: [
        candidate({ service: "WFS", type_names: ["RBSN_RR", "RBSN_FF"] }),
      ],
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
    expect(
      screen.getByText("serviceCandidates.openInMap").closest("button"),
    ).toHaveTextContent("serviceCandidates.openInMap");
  });

  it("keeps an unsupported feature type service as an explicit state", () => {
    state.resolution = resolution({
      candidates: [
        candidate({
          url: WFS_URL,
          original_url: WFS_URL,
          service: "WFS",
          advertised_version: "2.0.0",
        }),
      ],
    }) as RecordResolution;
    state.validation = {
      state: "unsupported",
      detail: "exception-report:OperationNotSupported",
    } as CandidateValidation;
    renderDialog();
    check();
    expect(
      screen.getByText("serviceCandidates.state.unsupported"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("exception-report:OperationNotSupported"),
    ).toBeInTheDocument();
    // the version the record advertised stays readable next to the refusal
    expect(screen.getByText("2.0.0")).toBeInTheDocument();
  });

  it("hands a feature type service which delivers over to the viewer", () => {
    state.resolution = resolution({
      candidates: [
        candidate({
          url: WFS_URL,
          original_url: WFS_URL,
          service: "WFS",
          type_names: ["RBSN_RR"],
        }),
      ],
    }) as RecordResolution;
    state.validation = {
      state: "resolved",
      service_type: "WFS",
      matched_names: ["RBSN_RR"],
    } as CandidateValidation;
    renderDialog();
    check();
    expect(
      screen.getByText("serviceCandidates.state.resolved"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText("maps.example.org/geoserver/ins/ows"));
    fireEvent.click(
      screen
        .getByText("serviceCandidates.openInMap")
        .closest("button") as HTMLButtonElement,
    );
    // the protocol is read from the delivered capabilities by the handoff
    expect(state.openInViewer).toHaveBeenCalledWith(WFS_URL);
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
      registered_targets: [
        { resource_type: "wms", id: 12, name: "Niederschlag" },
      ],
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

  it("links a registered element to its own screen", () => {
    // a dataset record is delivered through the layer which points back at it,
    // so the layer is what the registry verified and what to open
    state.resolution = resolution({
      registered_targets: [
        {
          resource_type: "layer",
          id: 44,
          name: "Verkehrsnetze",
          service_id: 12,
        },
      ],
    }) as RecordResolution;
    renderDialog();
    expect(screen.getByText("Verkehrsnetze")).toBeInTheDocument();
    expect(screen.getByText("ra.action.show")).toHaveAttribute("href", "#Layer");
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
    expect(
      screen.getByText("serviceCandidates.error.denied"),
    ).toBeInTheDocument();
  });

  it("registers nothing while the endpoints are only listed", () => {
    state.resolution = resolution({
      candidates: [candidate({ service: "WMS" })],
    }) as RecordResolution;
    renderDialog();
    // the action belongs to a selection, and a selection is only a selection
    expect(screen.queryByText(/^Register /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Form of/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("maps.example.org/geoserver/ins"));
    expect(screen.getByText(`Register ${WMS_URL}`)).toBeInTheDocument();
    expect(screen.queryByText(/^Form of/)).not.toBeInTheDocument();
    expect(state.openInViewer).not.toHaveBeenCalled();
  });

  it("opens the registration of the selected endpoint only", () => {
    state.resolution = resolution({
      candidates: [
        candidate({ service: "WMS" }),
        candidate({ url: WFS_URL, original_url: WFS_URL, service: "WFS" }),
      ],
    }) as RecordResolution;
    renderDialog();
    fireEvent.click(screen.getByText("maps.example.org/geoserver/ins/ows"));
    fireEvent.click(screen.getByText(`Register ${WFS_URL}`));
    expect(
      screen.getByText(`Form of WebMapService for ${WFS_URL}`),
    ).toBeInTheDocument();
    // a form is confirmed by its own save button, not by the map handoff
    expect(
      screen.queryByText("serviceCandidates.openInMap"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.registration.description"),
    ).toBeInTheDocument();
  });

  it("returns from the registration review to the endpoints with its answers", () => {
    state.resolution = resolution({
      candidates: [candidate({ service: "WMS" })],
    }) as RecordResolution;
    state.validation = {
      state: "resolved",
      service_type: "WMS",
      service_version: "1.3.0",
    } as CandidateValidation;
    renderDialog();
    check();
    fireEvent.click(screen.getByText(`Register ${WMS_URL}`));
    expect(screen.getByText(/^Form of/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("serviceCandidates.registration.back"));
    expect(screen.queryByText(/^Form of/)).not.toBeInTheDocument();
    // what the endpoint answered is still told by the row
    expect(
      screen.getByText("serviceCandidates.state.resolved"),
    ).toBeInTheDocument();
  });
});
