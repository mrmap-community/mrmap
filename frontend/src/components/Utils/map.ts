import type { Extent } from 'ol/extent';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import type BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';

export function wgs84ToScreen(geom: Geometry): Geometry {
  return geom.clone().transform('EPSG:4326', 'EPSG:900913');
}

export function screenToWgs84(geom: Geometry): Geometry {
  return geom.clone().transform('EPSG:900913', 'EPSG:4326');
}

export function zoomTo(
  map: OlMap,
  geometryOrExtent: Feature<Geometry> | Geometry | Extent | undefined,
): void {
  let value = geometryOrExtent;
  if (value instanceof Feature) {
    value = value.getGeometry();
  }
  if (value instanceof Geometry) {
    value = value.getExtent();
  }
  if (value) {
    map.getView().fit(value, {
      padding: [100, 100, 100, 100],
    });
  }
}

export function getAllSubtreeLayers(root: BaseLayer): BaseLayer[] {
  const layers: BaseLayer[] = [];
  const addAllSubtreeLayers = (layer: BaseLayer) => {
    layers.push(layer);
    if (layer instanceof LayerGroup) {
      layer.getLayers().forEach((childLayer) => addAllSubtreeLayers(childLayer));
    }
  };
  addAllSubtreeLayers(root);
  return layers;
}

//
// Application-wide map configuration
//
const backgroundLayersLayerGroup = new LayerGroup({
  // @ts-ignore
  properties: {
    name: 'mrmap-baselayers',
  },
  layers: [
    new OlLayerTile({
      properties: {
        name: 'osm',
      },
      source: new OlSourceOsm(),
    }),
  ],
});

const center = [788453.4890155146, 6573085.729161344]; //BONN

export const olMap = new OlMap({
  view: new OlView({
    center: center,
    zoom: 1, // to show the whole world
  }),
  layers: [backgroundLayersLayerGroup],
});
