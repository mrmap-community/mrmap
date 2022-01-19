import Collection from "ol/Collection";
import GML2 from 'ol/format/GML2';
import BaseLayer from "ol/layer/Base";
import LayerGroup from "ol/layer/Group";
import ImageLayer from "ol/layer/Image";
import OlMap from 'ol/Map';
import OlMapBrowserEvent from 'ol/MapBrowserEvent';
import * as olProj from 'ol/proj';
import ImageWMS from "ol/source/ImageWMS";
import { CreateLayerOpts } from "../Components/LayerManager/LayerManagerTypes";

export class LayerUtils {
    
  public getAllMapLayers(collection: OlMap | LayerGroup): (LayerGroup | BaseLayer | ImageLayer<ImageWMS>)[] {
    if (!(collection instanceof OlMap) && !(collection instanceof LayerGroup)) {
      console.error('Input parameter collection must be from type `ol.Map` or `ol.layer.Group`.');
      return [];
    }
      
    const layers = collection.getLayers().getArray();
    const allLayers:any = [];
      
    layers.forEach((layer) => {
      if (layer instanceof LayerGroup) {
        this.getAllMapLayers(layer).forEach((layeri:any) => allLayers.push(layeri));
      }
      allLayers.push(layer);
    });
        
    return allLayers;
  }

  public createMrMapOlWMSLayer(opts: CreateLayerOpts): ImageLayer<ImageWMS> {
    const olLayerSource = new ImageWMS({
      url: opts.url,
      params: {
        'LAYERS': opts.layers,
        'VERSION': opts.version,
        'FORMAT': opts.format,
        'TRANSPARENT': true
      },
      serverType: opts.serverType
    });
      
    const olWMSLayer = new ImageLayer({
      source: olLayerSource,
      visible: opts.visible,
    });
      
    olWMSLayer.setProperties({
      ...opts.properties,
      key: opts.layerId,
      layerId: opts.layerId,
      legendUrl: opts.legendUrl,
      title: opts.title,
      description: opts.description,
      extent: opts.extent
      // parent: opts.parent,
    });
      
    return olWMSLayer;
  }

  public getLayerByMrMapLayerId(
    collection: OlMap | LayerGroup, 
    id: string | number
  ): LayerGroup | BaseLayer | ImageLayer<ImageWMS> | undefined {
    const layersToSearch = this.getAllMapLayers(collection);
    return layersToSearch.find((layer:any) => String(layer.getProperties().layerId) === String(id));
  }

  private getLayerGroupByGroupTitle = (
    collection: OlMap | LayerGroup, 
    layerGroupTitle: string
  ): LayerGroup | undefined => {
    const requiredLayerGroup = this.getAllMapLayers(collection)
      .find((layer:any) => layer.getProperties().title === layerGroupTitle);
    if(requiredLayerGroup instanceof LayerGroup){
      return requiredLayerGroup;
    }
  };

  private getLayerGroupByMrMapLayerId(
    collection: OlMap | LayerGroup, 
    id: string|number
  ): LayerGroup | undefined {
    const allMapLayers = this.getAllMapLayers(collection);
    const requiredLayerGroup = allMapLayers
      .find((layer:any) => layer.getProperties().layerId === id);
    if(requiredLayerGroup) {
      if(requiredLayerGroup instanceof LayerGroup) {
        return requiredLayerGroup;
      } else {
        if(requiredLayerGroup.getProperties().parent) {
          const parentLayer = allMapLayers
            .find((layer:any) => layer.getProperties().layerId === requiredLayerGroup.getProperties().parent);
          if(parentLayer && parentLayer instanceof LayerGroup) {
            return parentLayer;
          }
        } else {
          if (collection instanceof LayerGroup) {
            return collection;
          }
          if (collection instanceof OlMap) {
            collection.getLayerGroup();
          }
        }
      }
    } else {
      if (collection instanceof LayerGroup) {
        return collection;
      }
      if (collection instanceof OlMap) {
        collection.getLayerGroup();
      }
    }
  }
      
  public addLayerToGroupByGroupTitle(
    collection: OlMap | LayerGroup, 
    layerGroupTitle: string, 
    layerToAdd: LayerGroup | BaseLayer
  ): void {
    const layerGroup: LayerGroup | undefined = this.getLayerGroupByGroupTitle(collection, layerGroupTitle);
    if(layerGroup) {
      const layerArray = layerGroup.getLayers().getArray();
      layerArray.push(layerToAdd);
      layerGroup.setLayers(new Collection(layerArray));
    } else {
      console.warn(`No layer group with the title ${layerGroupTitle}, was found on the map`);
    }
  }
      
  public addLayerToGroupByMrMapLayerId(
    collection: OlMap | LayerGroup, 
    id: string | number, 
    layerToAdd: LayerGroup | BaseLayer
  ): void {
    const layerGroup: LayerGroup | undefined = this.getLayerGroupByMrMapLayerId(collection, id);
    if(layerGroup) {
      const layerArray = layerGroup.getLayers().getArray();
      layerArray.push(layerToAdd);
      layerGroup.setLayers(new Collection(layerArray));
    } else {
      console.warn(`No layer group with the id ${id}, was found on the map`);
    }
  }

  private getWMSFeatureInfoUrl(
    olMap: OlMap, 
    layerSource: ImageWMS, 
    coordinates: [number, number]
  )
  : (string | undefined) {
  // all getFeatureInfo operation will be handled in EPSG:3857
  const featureInfoUrl: string | undefined = layerSource
      .getFeatureInfoUrl(
          coordinates,
          //@ts-ignore
          olMap.getView().getResolution(),
          'EPSG:3857',
          {
              'INFO_FORMAT': 'application/vnd.ogc.gml'
          }
      );
  return featureInfoUrl;
 }

 private async resolveWMSPromise(url: string): Promise<any> {
  try {
    const response = await fetch(url,
      { 
        method: 'GET', 
        //@ts-ignore
        headers: { 
          'Content-Type': 'application/vnd.ogc.gml',
          'Referer': 'http://localhost:3000'
        }
      } 
    );
    const textRes = await response.text();
    const format = new GML2();
    const fc = format.readFeatures(textRes);
    let result;
    fc.forEach((feature: any) => {
      if (Object.getOwnPropertyNames(feature).length > 0) {
        // TODO where to render the properties?
        result = feature.getProperties();
      } else{
        result = 'not found';
      }
    });
    return result;
  } catch (error) {
    //@ts-ignore
    throw new Error(error);
  }
}

 public getFeatureAttributes(olMap: OlMap, event: OlMapBrowserEvent<any>): any {
    const clickedPixel = olMap.getEventPixel(event.originalEvent);
    const clickedCoordinate = olMap.getCoordinateFromPixel(clickedPixel);

    // WARNING: The coordinates are directly transformed from the canvas pixel. This means that when the user
    // clicks on the center representation of the map in the canvas, the coordinates are correct according to the
    // current projection. HOWEVER... if the user zooms out, and zooms in again to another representation area of
    // the map within the canvas, the coordinates are not correct according to real world coordinates, rather they
    // are referenced according to the canvas axis. To fix this, we need to convert the derived coordinates from
    // the pixel using the OL method toLonLat().
    const realCoordinates = olProj.toLonLat(clickedCoordinate);
    // Altought it is said in the OL documentation that this coordinates are given by default in the map projection,
    // they are actually given in EPSG:4326 (even if specified). This might be a bug that will be investigated and
    // reported. Since we need the coordinates in EPSG:3857, we need to also get the proper transformation.

    // get the coordinates in EPSG:3857 (our default map projection)
    const transformedClickedCoordinate = olProj
      .transform(realCoordinates, 'EPSG:4326', olMap.getView().getProjection());

    const coords = transformedClickedCoordinate as [number, number];
    
    return olMap.forEachLayerAtPixel(
      clickedPixel,
      (layer: ImageLayer<ImageWMS>) => {
        // gets the layer source
        const layerSource: ImageWMS = layer.getSource();

        if (layerSource instanceof ImageWMS) {
          const featureInfoUrl = this.getWMSFeatureInfoUrl(olMap, layerSource, coords);
          if (featureInfoUrl) {
            return this.resolveWMSPromise(featureInfoUrl);
          }
        }

        return false;
      },
      { hitTolerance: 1 }
    );
  }

}
