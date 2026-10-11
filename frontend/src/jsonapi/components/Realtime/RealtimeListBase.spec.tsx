import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CrudEvent } from "../../../providers/dataProvider";
import RealtimeListBase from "./RealtimeListBase";

const state = vi.hoisted(() => ({
  data: [
    { id: 1, title: "One" },
    { id: 2, title: "Two" },
  ],
  resource: "Service",
  callbacks: new Map<string, Set<(event: CrudEvent) => void>>(),
}));
const provider = vi.hoisted(() => ({
  subscribe: vi.fn((topic: string, callback: (event: CrudEvent) => void) => {
    const callbacks = state.callbacks.get(topic) ?? new Set();
    callbacks.add(callback);
    state.callbacks.set(topic, callbacks);
  }),
  unsubscribe: vi.fn((topic: string, callback: (event: CrudEvent) => void) =>
    state.callbacks.get(topic)?.delete(callback),
  ),
}));
vi.mock("react-admin", () => ({
  useListController: () => ({ data: state.data, resource: state.resource }),
  useDataProvider: () => provider,
  useIsAuthPending: () => false,
  OptionalResourceContextProvider: ({
    children,
  }: {
    children: React.ReactNode;
  }) => children,
  ListContextProvider: ({ value }: { value: { data: unknown } }) => (
    <output>{JSON.stringify(value.data)}</output>
  ),
}));
beforeEach(() => {
  state.data = [
    { id: 1, title: "One" },
    { id: 2, title: "Two" },
  ];
  state.resource = "Service";
  state.callbacks.clear();
  vi.clearAllMocks();
});
const emit = (records: { id: number; title: string }[]) =>
  act(() => {
    state.callbacks
      .get("resource/Service/1")
      ?.forEach((callback) =>
        callback({
          type: "updated",
          payload: { ids: records.map((record) => record.id), records },
        }),
      );
  });
describe("RealtimeListBase", () => {
  it("updates the first row and multiple rows without losing sequential events", () => {
    render(<RealtimeListBase />);
    emit([
      { id: 1, title: "First update" },
      { id: 2, title: "Second update" },
    ]);
    emit([{ id: 1, title: "Latest" }]);
    expect(screen.getByRole("status")).toHaveTextContent("Latest");
    expect(screen.getByRole("status")).toHaveTextContent("Second update");
  });
  it("replaces subscriptions on refresh and cleans up when the resource changes or unmounts", () => {
    const { rerender, unmount } = render(<RealtimeListBase />);
    state.data = [{ id: 1, title: "Refetched" }];
    rerender(<RealtimeListBase />);
    expect(state.callbacks.get("resource/Service/1")?.size).toBe(1);
    expect(state.callbacks.get("resource/Service/2")?.size).toBe(0);
    expect(screen.getByRole("status")).toHaveTextContent("Refetched");
    state.resource = "Layer";
    rerender(<RealtimeListBase />);
    expect(state.callbacks.get("resource/Service/1")?.size).toBe(0);
    expect(state.callbacks.get("resource/Layer/1")?.size).toBe(1);
    unmount();
    expect(
      [...state.callbacks.values()].every((callbacks) => callbacks.size === 0),
    ).toBe(true);
  });
});
