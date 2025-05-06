import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { createControlComponent } from "@react-leaflet/core";
import * as L from "leaflet";

interface Props extends L.ControlOptions {
  position: L.ControlPosition;
  drawMarker?: boolean;
  drawCircleMarker?: boolean;
  drawPolyline?: boolean;
  drawRectangle?: boolean;
  drawPolygon?: boolean;
  drawCircle?: boolean;
  drawText?: boolean;

  oneBlock?: boolean;
  rotateMode?: boolean;

}

const Geoman = L.Control.extend({
  options: {},
  initialize(options: Props) {
    L.setOptions(this, options);
  },

  addTo(map: L.Map) {
    if (!map.pm) return;

    map.pm.addControls({
      ...this.options,
    });
  },
});

const createGeomanInstance = (props: Props) => {
  return new Geoman(props);
};

export const GeomanControl = createControlComponent(createGeomanInstance);