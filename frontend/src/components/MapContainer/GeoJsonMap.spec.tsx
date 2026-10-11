import { render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import GeoJsonField from "../Field/GeoJsonField";
import GeoJsonInput from "../Input/GeoJsonInput";

const editor = vi.hoisted(() => ({ mounts: vi.fn(), unmounts: vi.fn() }));
vi.mock("../Input/FeatureGroupEditor", async () => {
  const { useEffect } = await import("react");
  return {
    default: ({ editable }: { editable: boolean }) => {
      useEffect(() => {
        editor.mounts();
        return () => editor.unmounts();
      }, []);
      return (
        <span>{editable ? "Editable geometry" : "Read-only geometry"}</span>
      );
    },
  };
});
vi.mock("./ResizeAbleMapContainer", () => ({ default: () => null }));
vi.mock("react-leaflet", () => ({
  MapContainer: ({
    children,
    style,
  }: PropsWithChildren<{ style: React.CSSProperties }>) => (
    <div data-testid="map" style={style}>
      {children}
    </div>
  ),
  TileLayer: () => <span>Basemap</span>,
}));
vi.mock("react-admin", () => ({
  useRecordContext: () => ({ id: 1 }),
  useTranslate: () => (key: string) => key,
  useFieldValue: () => undefined,
  sanitizeFieldRestProps: () => ({}),
  useInput: () => ({ id: "geometry", field: { value: undefined } }),
  TextInput: () => <input aria-label="Geometry" />,
}));
vi.mock("react-hook-form", () => ({
  useFormContext: () => ({ setValue: vi.fn() }),
}));

describe("shared GeoJSON map", () => {
  it("renders a full-width map and read-only geometry for fields", () => {
    render(<GeoJsonField source="geometry" />);
    expect(screen.getByTestId("map")).toHaveStyle({
      width: "100%",
      height: "100%",
    });
    expect(screen.getByText("Read-only geometry")).toBeInTheDocument();
    expect(screen.getByText("Basemap")).toBeInTheDocument();
  });
  it("keeps the editor mounted when an input rerenders and forwards disabled state", () => {
    editor.mounts.mockClear();
    editor.unmounts.mockClear();
    const { rerender } = render(<GeoJsonInput source="geometry" />);
    expect(screen.getByText("Editable geometry")).toBeInTheDocument();
    rerender(<GeoJsonInput source="geometry" disabled />);
    expect(screen.getByText("Read-only geometry")).toBeInTheDocument();
    expect(editor.mounts).toHaveBeenCalledTimes(1);
    expect(editor.unmounts).not.toHaveBeenCalled();
  });
});
