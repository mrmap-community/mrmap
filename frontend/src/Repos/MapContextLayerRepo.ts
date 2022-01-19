import Cookies from 'js-cookie';
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';


export interface MapContextLayerCreate {
    name: string;
    title?: string;
    lft?: string;
    rght?: string;
    tree?: string;
    datasetMetadata?: string;
    renderingLayer?: string;
    parent?: string;
    layerScaleMax?: string;
    layerScaleMin?: string;
    layerStyleId?: string;
    selectionLayerId?: string;
    mapContextId: string
    parentLayerId?: string;
    isLeaf?: boolean;
}

type MapContextLayerAttributesUpdate = {
  name: string;
  title?: string;
  lft?: string;
  rght?: string;
  tree?: string;
  datasetMetadata?: string;
  renderingLayer?: string;
  parent?: string;
  layerScaleMax?: string;
  layerScaleMin?: string;
  layerStyleId?: string;
  selectionLayerId?: string;
};

class MapContextLayerRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontextlayers/', 'Kartenebenen');
  }

  async move (
    id: number|string,
    target: number|string,
    position: number|string = 'left'
  ) : Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    return await client['move_to' + this.resourcePath + '{id}/move_to/'](id, {
      data: {
        type: 'MapContextLayer',
        attributes: {
          target,
          position
        }
      }
    }, {
      headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') }
    });
  }

  async create (create: MapContextLayerCreate): Promise<JsonApiResponse> {
    const attributes:any = {
      name: create.name,
      title: create.title,
      layer_scale_max: create.layerScaleMax, //eslint-disable-line
      layer_scale_min: create.layerScaleMin, //eslint-disable-line
      layer_style_id: create.layerStyleId, //eslint-disable-line
    };
    const relationships:any = {
      map_context: { // eslint-disable-line
        data: {
          type: 'MapContext',
          id: create.mapContextId
        }
      }
    };
    if (create.parentLayerId) {
      relationships.parent = {
        data: {
          type: 'MapContextLayer',
          id: create.parentLayerId
        }
      };
    }
    if (create.datasetMetadata) {
      relationships.dataset_metadata = { // eslint-disable-line
        data: {
          type: 'DatasetMetadata',
          id: create.datasetMetadata
        }
      };
    }
    if (create.renderingLayer) {
      relationships.rendering_layer = { // eslint-disable-line
        data: {
          type: 'Layer',
          id: create.renderingLayer
        }
      };
    }
    if (create.selectionLayerId) {
      relationships.selection_layer = { // eslint-disable-line
        data: {
          type: 'FeatureType',
          id: create.selectionLayerId
        }
      };
    }
    return this.add('MapContextLayer', attributes, relationships);
  }

  async update (id:string, attributesToUpdate: MapContextLayerAttributesUpdate): Promise<JsonApiResponse> {
    const attributes:any = {
      name: attributesToUpdate.name,
      title: attributesToUpdate.title,
      layer_scale_max: attributesToUpdate.layerScaleMax, //eslint-disable-line
      layer_scale_min: attributesToUpdate.layerScaleMin, //eslint-disable-line
      layer_style_id: attributesToUpdate.layerStyleId, //eslint-disable-line
    };

    const relationships:any = {};

    if (attributesToUpdate.datasetMetadata) {
      relationships.dataset_metadata = { // eslint-disable-line
        data: {
          type: 'DatasetMetadata',
          id: attributesToUpdate.datasetMetadata
        }
      };
    }
    if (attributesToUpdate.renderingLayer) {
      relationships.rendering_layer = { // eslint-disable-line
        data: {
          type: 'Layer',
          id: attributesToUpdate.renderingLayer
        }
      };
    }
    if (attributesToUpdate.selectionLayerId) {
      relationships.selection_layer = { // eslint-disable-line
        data: {
          type: 'FeatureType',
          id: attributesToUpdate.selectionLayerId
        }
      };
    }
    return this.partialUpdate(id, 'MapContextLayer', attributes, relationships);
  }
}

export default MapContextLayerRepo;
