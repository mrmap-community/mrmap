import { Extent } from 'ol/extent';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import OlMap from 'ol/Map';

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
