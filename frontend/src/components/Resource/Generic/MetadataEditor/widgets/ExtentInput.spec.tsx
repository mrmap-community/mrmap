import type { ReactNode } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ExtentInput from "./ExtentInput";

// the map editor is GeoJSON plus leaflet; its own specs cover the drawing.
// here the widget contract is which drawing tools and which hint it provides
interface GeoJsonInputProbe {
  source?: string;
  drawRectangle?: boolean;
  drawPolygon?: boolean;
  helperText?: ReactNode;
}
const passed = vi.hoisted(() => ({ props: [] as GeoJsonInputProbe[] }));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
vi.mock("../../../../Input/GeoJsonInput", () => ({
  default: (props: GeoJsonInputProbe) => {
    passed.props.push(props);
    return <div>geojson input{props.helperText}</div>;
  },
}));

describe("ExtentInput", () => {
  it("draws bounding boxes by default and reminds about the CRS", () => {
    render(<ExtentInput source="boundingGeometry" label="Extent" />);
    expect(screen.getByText("geojson input")).toBeInTheDocument();
    expect(passed.props[0]?.drawRectangle).toBe(true);
    expect(passed.props[0]?.drawPolygon).toBe(false);
    expect(passed.props[0]?.source).toBe("boundingGeometry");
    expect(screen.getByText("wgs84Hint")).toBeInTheDocument();
  });

  it("switches the drawing tools with the mode", () => {
    render(<ExtentInput source="boundingGeometry" label="Extent" />);
    fireEvent.click(screen.getByText("polygon"));
    const last = passed.props[passed.props.length - 1];
    expect(last?.drawRectangle).toBe(false);
    expect(last?.drawPolygon).toBe(true);
  });

  it("keeps the schema helper text next to the hint", () => {
    render(
      <ExtentInput
        source="boundingGeometry"
        label="Extent"
        helperText="from the schema"
      />,
    );
    expect(screen.getByText(/from the schema/)).toBeInTheDocument();
    expect(screen.getByText("wgs84Hint")).toBeInTheDocument();
  });
});
