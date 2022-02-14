import { Extent } from 'ol/extent';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import LayerGroup from 'ol/layer/Group';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';

export function wgs84ToScreen (geom: Geometry): Geometry {
  return geom.clone().transform('EPSG:4326', 'EPSG:900913');
}

export function screenToWgs84 (geom: Geometry): Geometry {
  return geom.clone().transform('EPSG:900913', 'EPSG:4326');
}

export function zoomTo (map: OlMap, geometryOrExtent: Feature<Geometry> | Geometry | Extent | undefined): void {
  if (geometryOrExtent instanceof Feature) {
    geometryOrExtent = geometryOrExtent.getGeometry();
  }
  if (geometryOrExtent instanceof Geometry) {
    geometryOrExtent = geometryOrExtent.getExtent();
  }
  geometryOrExtent && map.getView().fit(geometryOrExtent, {
    padding: [100,100,100,100]
  });
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
    })
  ]
});

const center = [788453.4890155146, 6573085.729161344]; //BONN

export const olMap = new OlMap({
  view: new OlView({
    center: center,
    zoom: 1 // to show the whole world
  }),
  layers: [backgroundLayersLayerGroup]
});
