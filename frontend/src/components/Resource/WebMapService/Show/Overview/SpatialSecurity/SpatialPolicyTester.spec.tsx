import { QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import {
  AdminContext,
  BasenameContextProvider,
  RecordContextProvider,
  testDataProvider,
  TextInput,
  type RaRecord,
  type GetListParams,
} from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFilterInputForOperation } from "../../../../../../jsonapi/hooks/useFilterInputForOperation";
import SpatialPolicyTester from "./SpatialPolicyTester";

vi.mock("../../../../../../jsonapi/hooks/useFilterInputForOperation", () => ({
  useFilterInputForOperation: vi.fn(),
}));
vi.mock("../../../../../MapContainer/GeoJsonMap", () => ({
  default: ({ children }: PropsWithChildren) => (
    <div data-testid="areas-map">{children}</div>
  ),
}));
vi.mock("../../../../../Input/FeatureGroupEditor", () => ({
  default: ({ geoJson }: { geoJson: { features: unknown[] } }) => (
    <span>Allowed polygons: {geoJson.features.length}</span>
  ),
}));
const state = { rules: [] as RaRecord[], error: false, hold: false };
const rule = {
  id: 1,
  allowedGroups: [{ id: "team" }],
  operations: [{ id: "map" }],
  securedLayers: [{ id: "layer" }],
  allowedArea: { type: "MultiPolygon", coordinates: [] },
};
const getList = vi.fn(
  async (
    _resource: string,
    params: {
      filter?: Record<string, string>;
      pagination?: { page: number; perPage: number };
    },
  ) => {
    if (state.error) throw new Error("Configuration unavailable");
    if (state.hold && params.filter?.access_group)
      return await new Promise<never>(() => {});
    const filter = params.filter ?? {};
    const matches = state.rules.filter(
      (item) =>
        (!filter.access_group ||
          !item.allowedGroups.length ||
          item.allowedGroups.some(
            (group: RaRecord) => group.id === filter.access_group,
          )) &&
        (!filter.access_user ||
          !item.allowedGroups.length ||
          item.allowedGroups.some(
            (group: RaRecord) =>
              filter.access_user === "alice" &&
              ["team", "other"].includes(String(group.id)),
          )) &&
        (!filter.operations__value ||
          item.operations.some(
            (operation: RaRecord) => operation.id === filter.operations__value,
          )) &&
        (!filter.secured_layers__id ||
          item.securedLayers.some(
            (layer: RaRecord) => layer.id === filter.secured_layers__id,
          )),
    );
    const size = Math.min(params.pagination?.perPage ?? 10, 2);
    const page = params.pagination?.page ?? 1;
    return {
      data: matches.slice((page - 1) * size, page * size),
      total: matches.length,
      pageInfo: { hasNextPage: page * size < matches.length },
    };
  },
);
const FilterInput = ({
  getListParams: _params,
  ...props
}: React.ComponentProps<typeof TextInput> & { getListParams?: unknown }) => (
  <TextInput {...props} />
);
const show = () =>
  render(
    <MemoryRouter>
      <AdminContext
        dataProvider={testDataProvider({
          getList: async <RecordType extends RaRecord>(
            resource: string,
            params: GetListParams,
          ) => {
            const result = await getList(resource, params);
            return { ...result, data: result.data as RecordType[] };
          },
        })}
        queryClient={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <BasenameContextProvider basename="/WebMapService/service/show">
          <RecordContextProvider value={{ id: "service" }}>
            <SpatialPolicyTester />
          </RecordContextProvider>
        </BasenameContextProvider>
      </AdminContext>
    </MemoryRouter>,
  );
const select = () => {
  fireEvent.change(screen.getByLabelText("spatialSecurity.group"), {
    target: { value: "team" },
  });
  fireEvent.change(screen.getByLabelText("spatialSecurity.operation"), {
    target: { value: "map" },
  });
  fireEvent.change(screen.getByLabelText("spatialSecurity.layer"), {
    target: { value: "layer" },
  });
};
beforeEach(() => {
  state.rules = [rule];
  state.error = false;
  state.hold = false;
  getList.mockClear();
  vi.mocked(useFilterInputForOperation).mockReturnValue(
    [
      "access_group",
      "access_user",
      "operations__value",
      "secured_layers__id",
    ].map((source) => ({ component: FilterInput, props: { source } })),
  );
});
describe("schema-driven spatial policy tester", () => {
  it("uses user permissions across groups and clears the alternative group filter", async () => {
    state.rules = [rule, { ...rule, id: 2, allowedGroups: [{ id: "other" }] }];
    show();
    select();
    await screen.findByText("Allowed polygons: 1");
    fireEvent.change(screen.getByLabelText("spatialSecurity.user"), {
      target: { value: "alice" },
    });
    expect(await screen.findByText("Allowed polygons: 2")).toBeInTheDocument();
    expect(screen.getByLabelText("spatialSecurity.group")).toHaveValue("");
    expect(getList).toHaveBeenCalledWith(
      "AllowedWebMapServiceOperation",
      expect.objectContaining({
        filter: {
          access_user: "alice",
          operations__value: "map",
          secured_layers__id: "layer",
        },
      }),
    );
    fireEvent.change(screen.getByLabelText("spatialSecurity.group"), {
      target: { value: "team" },
    });
    expect(await screen.findByText("Allowed polygons: 1")).toBeInTheDocument();
    expect(screen.getByLabelText("spatialSecurity.user")).toHaveValue("");
  });
  it("limits users without matching groups to shared rules", async () => {
    state.rules = [rule, { ...rule, id: 2, allowedGroups: [] }];
    show();
    fireEvent.change(screen.getByLabelText("spatialSecurity.user"), {
      target: { value: "no-groups" },
    });
    fireEvent.change(screen.getByLabelText("spatialSecurity.operation"), {
      target: { value: "map" },
    });
    fireEvent.change(screen.getByLabelText("spatialSecurity.layer"), {
      target: { value: "layer" },
    });
    expect(await screen.findByText("Allowed polygons: 1")).toBeInTheDocument();
  });
  it("uses schema filters in a scoped list and updates access when the group changes", async () => {
    show();
    expect(useFilterInputForOperation).toHaveBeenCalledWith(
      "list_related_AllowedWebMapServiceOperation_of_WebMapService",
    );
    select();
    expect(
      await screen.findByText("spatialSecurity.restricted"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("areas-map")).toBeInTheDocument();
    expect(getList).toHaveBeenCalledWith(
      "AllowedWebMapServiceOperation",
      expect.objectContaining({
        filter: {
          access_group: "team",
          operations__value: "map",
          secured_layers__id: "layer",
        },
        meta: { relatedResource: { resource: "WebMapService", id: "service" } },
      }),
    );
    fireEvent.change(screen.getByLabelText("spatialSecurity.group"), {
      target: { value: "other" },
    });
    expect(
      await screen.findByText("spatialSecurity.denied"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("areas-map")).not.toBeInTheDocument();
  });
  it("loads every matching page before displaying the complete area", async () => {
    state.rules = [rule, { ...rule, id: 2 }, { ...rule, id: 3 }];
    show();
    select();
    expect(await screen.findByText("Allowed polygons: 3")).toBeInTheDocument();
    expect(getList).toHaveBeenCalledWith(
      "AllowedWebMapServiceOperation",
      expect.objectContaining({ pagination: { page: 2, perPage: 100 } }),
    );
  });
  it("keeps unrestricted access for a service without rules", async () => {
    state.rules = [];
    show();
    select();
    expect(
      await screen.findByText("spatialSecurity.unrestricted"),
    ).toBeInTheDocument();
  });
  it("includes rules applying to every group", async () => {
    state.rules = [{ ...rule, allowedGroups: [] }];
    show();
    select();
    expect(
      await screen.findByText("spatialSecurity.restricted"),
    ).toBeInTheDocument();
  });
  it("clears the previous map while changed filters are loading", async () => {
    show();
    select();
    await screen.findByTestId("areas-map");
    state.hold = true;
    fireEvent.change(screen.getByLabelText("spatialSecurity.group"), {
      target: { value: "other" },
    });
    await waitFor(() =>
      expect(screen.queryByTestId("areas-map")).not.toBeInTheDocument(),
    );
  });
  it("reports configuration errors without displaying permissions", async () => {
    state.error = true;
    show();
    select();
    expect(
      await screen.findByText("spatialSecurity.loadError"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("areas-map")).not.toBeInTheDocument();
  });
  it("identifies missing schema filters instead of inventing selectors", () => {
    vi.mocked(useFilterInputForOperation).mockReturnValue([]);
    show();
    expect(
      screen.getByText("spatialSecurity.schemaUnavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
  it("preserves the proxy settings tab link", () => {
    show();
    expect(
      screen.getByRole("link", { name: "serviceShow.proxy" }),
    ).toHaveAttribute("href", "/WebMapService/service/show/ProxySetting");
  });
});
