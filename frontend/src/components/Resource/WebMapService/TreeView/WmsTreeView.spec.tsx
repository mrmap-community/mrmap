import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WmsTreeView from "./WmsTreeView";

const { scrollTo, bounds } = vi.hoisted(() => ({
  scrollTo: vi.fn(),
  bounds: { top: 600, bottom: 632, height: 32 },
}));
vi.mock("../../../utils", async () => {
  const { TreeItem } = await import("@mui/x-tree-view/TreeItem");
  return {
    useQueryParam: () => ["layer-1", vi.fn()],
    getSubTree: () =>
      ["layer-1", "layer-2"].map((id) => (
        <TreeItem
          key={id}
          itemId={id}
          label={id}
          slotProps={{
            content: {
              ref: (node: HTMLDivElement | null) => {
                if (node) node.getBoundingClientRect = () => bounds as DOMRect;
              },
            },
          }}
        />
      )),
  };
});
vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  useRecordContext: () => undefined,
}));
let frames: FrameRequestCallback[] = [];
beforeEach(() => {
  frames = [];
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  scrollTo.mockClear();
  bounds.top = 600;
  bounds.bottom = 632;
});
afterEach(() => vi.unstubAllGlobals());
const renderTree = (selectedItems = "layer-1") => {
  const result = render(
    <WmsTreeView
      record={{ id: "service", layers: [] }}
      selectedItems={selectedItems}
      focusSelectedLayer
    />,
  );
  const tree = result.getByRole("tree");
  tree.getBoundingClientRect = () => ({ top: 100, bottom: 500 }) as DOMRect;
  Object.defineProperty(tree, "clientHeight", { value: 400 });
  tree.scrollTo = scrollTo;
  act(() => {
    frames.splice(0).forEach((callback) => callback(0));
  });
  return { ...result, tree };
};
describe("layer selection scrolling with the real MUI tree", () => {
  it("reveals the selected item using MUI's DOM lookup", () => {
    const { getByRole } = renderTree();
    expect(getByRole("treeitem", { name: "layer-1" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(scrollTo).toHaveBeenCalledWith({ top: 316, behavior: "smooth" });
  });
  it("uses the controlled selection instead of the URL default", () => {
    const { getByRole } = renderTree("layer-2");
    expect(getByRole("treeitem", { name: "layer-2" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(scrollTo).toHaveBeenCalledWith({ top: 316, behavior: "smooth" });
  });
  it("checks visibility again when ancestor expansion finishes", () => {
    bounds.top = 200;
    bounds.bottom = 232;
    const { tree } = renderTree();
    expect(scrollTo).not.toHaveBeenCalled();
    bounds.top = 600;
    bounds.bottom = 632;
    fireEvent.transitionEnd(tree);
    expect(scrollTo).toHaveBeenCalledWith({ top: 316, behavior: "smooth" });
  });
  it("keeps the scroll position when the selected layer is already visible", () => {
    bounds.top = 200;
    bounds.bottom = 232;
    renderTree();
    expect(scrollTo).not.toHaveBeenCalled();
  });
});
