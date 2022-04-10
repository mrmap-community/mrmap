import Collection from 'ol/Collection';
import type BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import type ImageLayer from 'ol/layer/Image';
import OlMap from 'ol/Map';
import type ImageWMS from 'ol/source/ImageWMS';

export class LayerUtils {
  public getAllMapLayers(
    collection: OlMap | LayerGroup,
  ): (LayerGroup | BaseLayer | ImageLayer<ImageWMS>)[] {
    if (!(collection instanceof OlMap) && !(collection instanceof LayerGroup)) {
      console.error('Input parameter collection must be from type `ol.Map` or `ol.layer.Group`.');
      return [];
    }

    const layers = collection.getLayers().getArray();
    const allLayers: any = [];

    layers.forEach((layer) => {
      if (layer instanceof LayerGroup) {
        this.getAllMapLayers(layer).forEach((layeri: any) => allLayers.push(layeri));
      }
      allLayers.push(layer);
    });

    return allLayers;
  }

  public getAllSubtreeLayers(root: BaseLayer): BaseLayer[] {
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

  public getLayerByMrMapLayerId(
    collection: OlMap | LayerGroup,
    id: string | number,
  ): LayerGroup | BaseLayer | ImageLayer<ImageWMS> | undefined {
    const layersToSearch = this.getAllMapLayers(collection);
    return layersToSearch.find(
      (layer: any) => String(layer.getProperties().layerId) === String(id),
    );
  }

  public getLayerGroupByGroupTitle = (
    collection: OlMap | LayerGroup,
    layerGroupTitle: string,
  ): LayerGroup | undefined => {
    const requiredLayerGroup = this.getAllMapLayers(collection).find(
      (layer: any) => layer.getProperties().title === layerGroupTitle,
    );
    if (requiredLayerGroup instanceof LayerGroup) {
      return requiredLayerGroup;
    }
    return undefined;
  };

  private getLayerGroupByMrMapLayerId(
    collection: OlMap | LayerGroup,
    id: string | number,
  ): LayerGroup | undefined {
    const allMapLayers = this.getAllMapLayers(collection);
    const requiredLayerGroup = allMapLayers.find(
      (layer: any) => layer.getProperties().layerId === id,
    );
    if (requiredLayerGroup) {
      if (requiredLayerGroup instanceof LayerGroup) {
        return requiredLayerGroup;
      } else {
        if (requiredLayerGroup.getProperties().parent) {
          const parentLayer = allMapLayers.find(
            (layer: any) =>
              layer.getProperties().layerId === requiredLayerGroup.getProperties().parent,
          );
          if (parentLayer && parentLayer instanceof LayerGroup) {
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
    return undefined;
  }

  public addLayerToGroupByGroupTitle(
    collection: OlMap | LayerGroup,
    layerGroupTitle: string,
    layerToAdd: LayerGroup | BaseLayer,
  ): void {
    const layerGroup: LayerGroup | undefined = this.getLayerGroupByGroupTitle(
      collection,
      layerGroupTitle,
    );
    if (layerGroup) {
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
    layerToAdd: LayerGroup | BaseLayer,
  ): void {
    const layerGroup: LayerGroup | undefined = this.getLayerGroupByMrMapLayerId(collection, id);
    if (layerGroup) {
      const layerArray = layerGroup.getLayers().getArray();
      layerArray.push(layerToAdd);
      layerGroup.setLayers(new Collection(layerArray));
    } else {
      console.warn(`No layer group with the id ${id}, was found on the map`);
    }
  }
}
