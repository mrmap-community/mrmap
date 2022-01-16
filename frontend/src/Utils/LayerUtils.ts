import Collection from "ol/Collection";
import BaseLayer from "ol/layer/Base";
import LayerGroup from "ol/layer/Group";
import ImageLayer from "ol/layer/Image";
import OlMap from 'ol/Map';
import ImageWMS from "ol/source/ImageWMS";
import { CreateLayerOpts } from "../Components/LayerTree/LayerTreeTypes";

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
      layerId: opts.layerId,
      legendUrl: opts.legendUrl,
      title: opts.title,
      name: opts.name,
      extent: opts.extent
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

  private getLayerGroupByName = (
    collection: OlMap | LayerGroup, 
    layerGroupName: string
  ): LayerGroup | undefined => {
    const requiredLayerGroup = this.getAllMapLayers(collection)
      .find((layer:any) => layer.getProperties().name === layerGroupName);
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
      
  public addLayerToGroupByName(
    collection: OlMap | LayerGroup, 
    layerGroupName: string, 
    layerToAdd: LayerGroup | BaseLayer
  ): void {
    const layerGroup: LayerGroup | undefined = this.getLayerGroupByName(collection, layerGroupName);
    if(layerGroup) {
      const layerArray = layerGroup.getLayers().getArray();
      layerArray.push(layerToAdd);
      layerGroup.setLayers(new Collection(layerArray));
    } else {
      console.warn(`No layer group with the name ${layerGroupName}, was found on the map`);
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
}
