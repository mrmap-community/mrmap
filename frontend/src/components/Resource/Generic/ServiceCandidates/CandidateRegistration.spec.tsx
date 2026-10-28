import type {
  CandidateValidation,
  RegisteredTarget,
  ServiceCandidate,
} from "./useServiceCandidates";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CandidateRegistrationButton,
  CandidateRegistrationForm,
  type RegistrationTarget,
} from "./CandidateRegistration";

const state = vi.hoisted(() => ({
  hasCreate: true,
  operations: [] as string[],
  notified: undefined as
    { resource: string; action: string; record: unknown } | undefined,
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string, args?: Record<string, unknown>) =>
    args ? `${key}:${JSON.stringify(args)}` : key,
  useResourceContext: () => "WebMapService",
  useResourceDefinition: () => ({ hasCreate: state.hasCreate }),
  Toolbar: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SaveButton: ({
    mutationOptions,
  }: {
    mutationOptions: { onSuccess: (record: unknown) => void };
  }) => (
    <button onClick={() => mutationOptions.onSuccess({ id: 7 })}>
      ra.action.save
    </button>
  ),
  ShowButton: ({
    label,
    resource,
    record,
  }: {
    label: string;
    resource: string;
    record: { id: number };
  }) => <a href={`#${resource}-${record.id}`}>{label}</a>,
}));

// the schema driven form is the house component; the spec answers what it is
// given, its own behaviour is covered by the jsonapi specs
vi.mock("../../../../jsonapi/components/CreateGuesser", () => ({
  default: ({
    resource,
    defaultValues,
    toolbar,
  }: {
    resource: string;
    defaultValues: { getCapabilitiesUrl: string };
    toolbar: React.ReactNode;
  }) => (
    <div>
      <span>form of {resource}</span>
      <span>prefilled: {defaultValues.getCapabilitiesUrl}</span>
      {toolbar}
    </div>
  ),
}));

vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (operationId?: string) =>
    operationId && state.operations.includes(operationId) ? {} : undefined,
}));

// the house notification path of a create, see jsonapi/hooks/useGuesserSuccess
vi.mock("../../../../jsonapi/hooks/useGuesserSuccess", () => ({
  default:
    ({ resource, action }: { resource: string; action: string }) =>
    (record: unknown) => {
      state.notified = { resource, action, record };
    },
}));

const WMS_URL =
  "https://maps.example.org/geoserver/ins?service=wms&version=1.3.0&request=GetCapabilities";
const WMS_QUALIFIED =
  "https://maps.example.org/geoserver/ins?service=WMS&request=GetCapabilities&version=1.3.0";

const candidate = (overrides: Record<string, unknown> = {}) =>
  ({
    url: WMS_URL,
    original_url: WMS_URL,
    kind: "capabilities",
    source: "own-distribution",
    state: "unvalidated",
    service: "WMS",
    ...overrides,
  }) as unknown as ServiceCandidate;

const resolved = (overrides: Record<string, unknown> = {}) =>
  ({
    state: "resolved",
    detail: "ok",
    service_type: "WMS",
    service_version: "1.3.0",
    registration_url: WMS_QUALIFIED,
    ...overrides,
  }) as unknown as CandidateValidation;

const target = (overrides: Partial<RegistrationTarget> = {}) =>
  ({
    resource: "WebMapService",
    candidate: candidate(),
    answer: resolved(),
    ...overrides,
  }) as RegistrationTarget;

const registered = (overrides: Record<string, unknown> = {}) =>
  ({
    resource_type: "wms",
    id: 12,
    name: "Already registered WMS",
    ...overrides,
  }) as unknown as RegisteredTarget;

const onRegister = vi.fn();
const onRegistered = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  state.hasCreate = true;
  state.operations = ["create_WebMapService", "create_WebFeatureService"];
  state.notified = undefined;
});

describe("offering the registration of a candidate", () => {
  it("offers the service the record names", () => {
    render(
      <CandidateRegistrationButton
        candidate={candidate()}
        onRegister={onRegister}
      />,
    );
    fireEvent.click(screen.getByText("serviceCandidates.registration.action"));
    expect(onRegister).toHaveBeenCalledWith({
      resource: "WebMapService",
      candidate: candidate(),
      answer: undefined,
    });
  });

  it("asks the resource the endpoint announced, not the advertised one", () => {
    const answer = resolved({ service_type: "WFS", service_version: "2.0.0" });
    render(
      <CandidateRegistrationButton
        candidate={candidate()}
        answer={answer}
        onRegister={onRegister}
      />,
    );
    fireEvent.click(screen.getByText("serviceCandidates.registration.action"));
    expect(onRegister).toHaveBeenCalledWith(
      expect.objectContaining({ resource: "WebFeatureService", answer }),
    );
  });

  it("states a reason instead of offering a service without a resource", () => {
    render(
      <CandidateRegistrationButton
        candidate={candidate({ service: "WMTS" })}
        onRegister={onRegister}
      />,
    );
    expect(onRegister).not.toHaveBeenCalled();
    expect(
      screen.getByText(/serviceCandidates.registration.unsupportedService/),
    ).toHaveTextContent("WMTS");
    expect(
      screen.queryByText("serviceCandidates.registration.action"),
    ).not.toBeInTheDocument();
  });

  it("states a reason when no service is named at all", () => {
    render(
      <CandidateRegistrationButton
        candidate={candidate({ service: null })}
        onRegister={onRegister}
      />,
    );
    expect(
      screen.getByText(/serviceCandidates\.registration\.unknownService/),
    ).toBeInTheDocument();
  });

  it("does not register an endpoint which refused", () => {
    render(
      <CandidateRegistrationButton
        candidate={candidate()}
        answer={
          resolved({
            state: "unavailable",
            detail: "exception-report:OperationNotSupported",
            registration_url: null,
          }) as CandidateValidation
        }
        onRegister={onRegister}
      />,
    );
    expect(
      screen.getByText(/serviceCandidates\.registration\.refused/),
    ).toBeInTheDocument();
    expect(onRegister).not.toHaveBeenCalled();
  });

  it("keeps the action away without a create right", () => {
    state.hasCreate = false;
    render(
      <CandidateRegistrationButton
        candidate={candidate()}
        onRegister={onRegister}
      />,
    );
    expect(
      screen.queryByText("serviceCandidates.registration.action"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.registration.noRights"),
    ).toBeInTheDocument();
  });

  it("keeps the action away when the api cannot register services", () => {
    state.operations = [];
    render(
      <CandidateRegistrationButton
        candidate={candidate()}
        onRegister={onRegister}
      />,
    );
    expect(
      screen.queryByText("serviceCandidates.registration.action"),
    ).not.toBeInTheDocument();
  });

  it("offers nothing without a selection", () => {
    const { container } = render(
      <CandidateRegistrationButton onRegister={onRegister} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("reviewing a registration", () => {
  const renderForm = (
    formTarget: RegistrationTarget,
    targets: RegisteredTarget[] = [],
  ) =>
    render(
      <CandidateRegistrationForm
        target={formTarget}
        registered={targets}
        sourceRecord="Verkehrsnetze (DE_HH_WMS_INSPIRE)"
        sourceDocument="de.hh.72796d51"
        onRegistered={onRegistered}
      />,
    );

  it("prefills the qualified endpoint the endpoint answered", () => {
    renderForm(target());
    expect(screen.getByText("form of WebMapService")).toBeInTheDocument();
    expect(screen.getByText(`prefilled: ${WMS_QUALIFIED}`)).toBeInTheDocument();
  });

  it("prefills the advertised endpoint while nothing was asked", () => {
    renderForm(target({ answer: undefined }));
    expect(screen.getByText(`prefilled: ${WMS_URL}`)).toBeInTheDocument();
  });

  it("tells record, advertised link and derived endpoint apart", () => {
    renderForm(
      target({
        candidate: candidate({
          url: WMS_QUALIFIED,
          original_url:
            "https://maps.example.org/geoserver/ins?service=wms&version=1.3.0&request=GetMap",
          derived: true,
        }),
      }),
    );
    expect(
      screen.getByText("serviceCandidates.registration.record"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Verkehrsnetze (DE_HH_WMS_INSPIRE)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.registration.document"),
    ).toBeInTheDocument();
    expect(screen.getByText("de.hh.72796d51")).toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.registration.advertised"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "https://maps.example.org/geoserver/ins?service=wms&version=1.3.0&request=GetMap",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceCandidates.registration.capabilities"),
    ).toBeInTheDocument();
    expect(screen.getByText(`prefilled: ${WMS_QUALIFIED}`)).toBeInTheDocument();
    expect(
      screen.getByText(/serviceCandidates\.registration\.answeredVersion/),
    ).toHaveTextContent("WMS");
  });

  it("links only the registration of the same resource as a duplicate", () => {
    renderForm(target(), [
      registered(),
      registered({ resource_type: "csw", id: 4, name: "Harvested catalogue" }),
    ]);
    expect(
      screen.getByText("serviceCandidates.registration.duplicate"),
    ).toBeInTheDocument();
    expect(screen.getByText("Already registered WMS")).toBeInTheDocument();
    expect(screen.getByText("ra.action.show")).toHaveAttribute(
      "href",
      "#WebMapService-12",
    );
    // a harvested catalogue is no duplicate of a map service and is not named
    expect(screen.queryByText("Harvested catalogue")).not.toBeInTheDocument();
    expect(screen.getByText(`prefilled: ${WMS_QUALIFIED}`)).toBeInTheDocument();
  });

  it("names the service a registered element belongs to", () => {
    // a dataset record is delivered through its layer and feature type, so the
    // element is what the registry verified - and its kind names the service
    // this registration would be added beside
    renderForm(target(), [
      registered({ resource_type: "layer", id: 44, name: "Verkehrsnetze" }),
      registered({ resource_type: "feature_type", id: 51, name: "RBSN_RR" }),
    ]);
    expect(screen.getByText("Verkehrsnetze")).toBeInTheDocument();
    expect(screen.getByText("ra.action.show")).toHaveAttribute(
      "href",
      "#Layer-44",
    );
    // a feature type of a feature service is no duplicate of a map service
    expect(screen.queryByText("RBSN_RR")).not.toBeInTheDocument();
  });

  it("says what a registration beside an existing one means", () => {
    renderForm(target(), [registered()]);
    expect(
      screen.getByText("serviceCandidates.registration.duplicateHint"),
    ).toBeInTheDocument();
  });

  it("says nothing about duplicates for a service none delivers", () => {
    renderForm(target(), []);
    expect(
      screen.queryByText("serviceCandidates.registration.duplicate"),
    ).not.toBeInTheDocument();
  });

  it("registers nothing until the form is saved", () => {
    renderForm(target());
    expect(onRegistered).not.toHaveBeenCalled();
    expect(state.notified).toBeUndefined();
    fireEvent.click(screen.getByText("ra.action.save"));
    expect(state.notified).toEqual({
      resource: "WebMapService",
      action: "created",
      record: { id: 7 },
    });
    // the existing background process surfaces report the task from here on
    expect(onRegistered).toHaveBeenCalledTimes(1);
  });
});
