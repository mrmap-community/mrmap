import { CoreAdminContext, ListContextProvider } from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  indicatorFilter,
  indicatorStates,
  withoutIndicatorKeys,
  MetadataIndicators,
} from "./MetadataIndicators";

const getList = vi.fn(async () => ({ data: [], total: 0 }));
const dataProvider = { getList, getMany: getList, getOne: getList } as never;

const setFilters = vi.fn();

const renderIndicators = (record: Record<string, unknown>) => render(
  <CoreAdminContext dataProvider={dataProvider}>
    <ListContextProvider value={{
      data: [], total: 0, isPending: false, resource: "DatasetMetadataRecord",
      filter: undefined, filterValues: { search: "water" }, setFilters,
    } as never}>
      <MetadataIndicators record={record as never} />
    </ListContextProvider>
  </CoreAdminContext>
);

describe("metadata indicator states", () => {
  it("keeps an absent attribute unknown and never renders it as a passed check", () => {
    const states = Object.fromEntries(indicatorStates({} as never).map(({ key, state }) => [key, state]));
    expect(states).toEqual({ broken: "unknown", quality: "unknown", licence: "unknown" });
  });

  it("distinguishes explicit false from unknown and empty quality from a finding", () => {
    const states = Object.fromEntries(indicatorStates({
      isBroken: false,
      insufficientQuality: "",
      licence: { data: { id: "cc0", type: "Licence" } },
    } as never).map(({ key, state }) => [key, state]));
    expect(states).toEqual({ broken: "ok", quality: "ok", licence: "ok" });
    const flagged = Object.fromEntries(indicatorStates({
      isBroken: true,
      insufficientQuality: "missing title",
      licence: { data: null },
    } as never).map(({ key, state }) => [key, state]));
    expect(flagged).toEqual({ broken: "error", quality: "warning", licence: "warning" });
  });

  it("names the filter of every choosable state", () => {
    expect(indicatorFilter("broken", "error")).toEqual({ is_broken: true });
    expect(indicatorFilter("quality", "warning")).toEqual({ has_insufficient_quality: true });
    expect(indicatorFilter("licence", "warning")).toEqual({ has_licence: false });
    expect(indicatorFilter("licence", "unknown")).toBeUndefined();
  });

  it("keeps the scope of a facet free of the indicator filters", () => {
    expect(withoutIndicatorKeys({ search: "water", has_licence: false })).toEqual({ search: "water" });
  });
});

describe("metadata indicator chips", () => {
  it("labels unknown records as unknown instead of fine", () => {
    renderIndicators({});
    expect(screen.getByText("metadataIndicators.broken.unknown")).toBeInTheDocument();
    expect(screen.queryByText("metadataIndicators.broken.ok")).not.toBeInTheDocument();
  });

  it("narrows the list to its state when a warning chip is clicked", () => {
    renderIndicators({ isBroken: false, insufficientQuality: "missing title", licence: { data: { id: "l" } } });
    fireEvent.click(screen.getByText("metadataIndicators.quality.warning"));
    // the click keeps the search of the list and replaces other indicator filters
    expect(setFilters).toHaveBeenCalledWith({ search: "water", has_insufficient_quality: true }, {});
  });
});
