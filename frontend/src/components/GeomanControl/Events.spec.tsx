import type { Layer } from "leaflet";

import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Events from "./Events";

/**
 * The map the component draws its listeners on, and the layer a draw action
 * hands them: both keep their handlers by event name, which is what lets a
 * spec fire an event the way leaflet would.
 */
type MapHandler = (event: { layer: Layer }) => void;

const state = vi.hoisted(() => {
  const mapListeners = new Map<string, MapHandler>();
  const held = {
    /** how often the component reached `map.on` - the guard is what counts here */
    registrations: 0,
    mapListeners,
    map: {
      hasEventListeners: (name: string) => mapListeners.has(name),
      on: (name: string, handler: MapHandler) => {
        mapListeners.set(name, handler);
        held.registrations += 1;
        return held.map;
      },
    },
  };
  return held;
});

vi.mock("react-leaflet", () => ({ useMap: () => state.map }));

/** a layer which answers `pm:update` and `pm:remove` like a leaflet one */
const aLayer = () => {
  const listeners = new Map<string, () => void>();
  return {
    fire: (name: string) => listeners.get(name)?.(),
    hasEventListeners: (name: string) => listeners.has(name),
    on: (name: string, handler: () => void) => {
      listeners.set(name, handler);
    },
  } as unknown as Layer & { fire: (name: string) => void };
};

const handlers = () => ({
  onCreate: vi.fn(),
  onUpdate: vi.fn(),
  onRemove: vi.fn(),
});

/** the create handler the component registered, fired as leaflet fires it */
const created = (layer: Layer) => {
  const handler = state.mapListeners.get("pm:create");
  if (handler === undefined) throw new Error("no pm:create listener");
  act(() => handler({ layer }));
};

beforeEach(() => {
  state.mapListeners.clear();
  state.registrations = 0;
});

describe("Events", () => {
  it("answers a draw by its own handler and watches the layer", () => {
    const first = handlers();
    render(<Events {...first} />);
    const layer = aLayer();
    created(layer);

    expect(first.onCreate).toHaveBeenCalledWith({ layer });
    // the layer is watched for its own edits only once it was created here
    expect(layer.hasEventListeners("pm:update")).toBe(true);
    expect(layer.hasEventListeners("pm:remove")).toBe(true);
  });

  it("dispatches the latest handlers, though the listener was registered once", () => {
    const first = handlers();
    const second = handlers();
    const view = render(<Events {...first} />);
    // every handler of the screen changed, the map's listener did not: it
    // must answer with the handlers of the current render and not with the
    // ones of the render which registered it (#1466)
    view.rerender(<Events {...second} />);

    const layer = aLayer();
    created(layer);
    expect(second.onCreate).toHaveBeenCalledTimes(1);
    expect(first.onCreate).not.toHaveBeenCalled();

    act(() => layer.fire("pm:update"));
    expect(second.onUpdate).toHaveBeenCalledTimes(1);
    expect(first.onUpdate).not.toHaveBeenCalled();

    act(() => layer.fire("pm:remove"));
    expect(second.onRemove).toHaveBeenCalledTimes(1);
    expect(first.onRemove).not.toHaveBeenCalled();
  });

  it("registers its create listener once per map", () => {
    const view = render(<Events {...handlers()} />);
    view.rerender(<Events {...handlers()} />);
    expect(state.registrations).toBe(1);
  });

  it("keeps an update listener the layer already carries", () => {
    const watched = handlers();
    render(<Events {...watched} />);
    const layer = aLayer();
    layer.on("pm:update", () => undefined);
    created(layer);

    expect(watched.onCreate).toHaveBeenCalledTimes(1);
    act(() => layer.fire("pm:update"));
    // the handler of the layer answered, not a second one from this screen
    expect(watched.onUpdate).not.toHaveBeenCalled();
  });
});
