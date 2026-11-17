import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, type RenderResult } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import ListServiceAlert from "./ListServiceAlert";

const state = vi.hoisted(() => ({
  /** the readiness of the realtime bus, ReadyState.CONNECTING is 0 */
  ready: 0,
}));

vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../../jsonapi/hooks/useFilterInputForOperation", () => ({
  useFilterInputForOperation: () => [],
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  DateField: () => null,
  FunctionField: () => null,
  TextField: () => null,
}));

/** the row of the attention list which names the state of an alert */
const alertRow = (record: RaRecord): RenderResult => {
  render(<ListServiceAlert />);
  const columns = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].columns ?? [];
  const column = columns.find((element) => element.key === "category");
  const renderCategory = (
    column?.props as unknown as { render: (record: RaRecord) => ReactNode }
  ).render;
  return render(<>{renderCategory(record)}</>);
};

beforeEach(() => {
  state.ready = 0;
});

describe("ListServiceAlert", () => {
  it("uses schema filters, realtime and polling, and links to the resolving workflow", () => {
    render(<ListServiceAlert />);
    const props = vi.mocked(ListGuesser).mock.calls[0][0];
    expect(props.realtime).toBe(true);
    // the bus carries the alert topic - the list only polls while it is down
    expect(props.refetchInterval).toBe(20000);
    state.ready = 1; // ReadyState.OPEN
    render(<ListServiceAlert />);
    expect(
      vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].refetchInterval,
    ).toBe(false);
    expect(props.sort).toEqual({ field: "severity,-occurredAt", order: "ASC" });
    const rowClick = props.dataGridProps?.rowClick;
    expect(typeof rowClick).toBe("function");
    if (typeof rowClick === "function") {
      expect(
        rowClick("a", "ServiceAlert", {
          id: "a",
          targetPath: "/WebMapServiceUpdateJob/2/show",
        }),
      ).toBe("/WebMapServiceUpdateJob/2/show");
    }
  });

  it("names the state of an alert by its name", () => {
    const { getByText, queryByText } = alertRow({
      id: "harvest_aborted:CatalogueService:1",
      category: "harvest_aborted",
      message: "harvest_aborted",
    });
    expect(getByText("serviceAlerts.categories.harvest_aborted")).toBeInTheDocument();
    // the message of such an alert is the name of its state and nothing else,
    // so it is not answered twice
    expect(queryByText("harvest_aborted")).not.toBeInTheDocument();
  });

  it("says what an alert has to tell about its state", () => {
    const { getByText } = alertRow({
      id: "harvest_schedule_too_tight:CatalogueService:1",
      category: "harvest_schedule_too_tight",
      message:
        'The schedule "*/5 * * * *" harvests this catalogue more often than a ' +
        "harvest of it takes: the harvests which finished measured 0:40:00 on " +
        "average.",
    });
    expect(
      getByText("serviceAlerts.categories.harvest_schedule_too_tight"),
    ).toBeInTheDocument();
    expect(getByText(/0:40:00/)).toBeInTheDocument();
  });
});
