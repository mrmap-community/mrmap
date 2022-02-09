import Cookies from 'js-cookie';

import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';


export interface MapContextLayerCreate {
    title: string;
    description?: string;
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
  title: string;
  description?: string;
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
    position: number|string
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
      title: create.title,
      description: create.description,
      layerScaleMax: create.layerScaleMax, 
      layerScaleMin: create.layerScaleMin, 
      layerStyleId: create.layerStyleId, 
    };
    const relationships:any = {
      mapContext: {
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
      relationships.datasetMetadata = {
        data: {
          type: 'DatasetMetadata',
          id: create.datasetMetadata
        }
      };
    }
    if (create.renderingLayer) {
      relationships.renderingLayer = {
        data: {
          type: 'Layer',
          id: create.renderingLayer
        }
      };
    }
    if (create.selectionLayerId) {
      relationships.selectionLayer = {
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
      description: attributesToUpdate.description,
      title: attributesToUpdate.title,
      layerScaleMax: attributesToUpdate.layerScaleMax, 
      layerScaleMin: attributesToUpdate.layerScaleMin, 
      layerStyleId: attributesToUpdate.layerStyleId, 
    };

    const relationships:any = {};

    if (attributesToUpdate.datasetMetadata) {
      relationships.datasetMetadata = {
        data: {
          type: 'DatasetMetadata',
          id: attributesToUpdate.datasetMetadata
        }
      };
    }
    if (attributesToUpdate.renderingLayer) {
      relationships.renderingLayer = {
        data: {
          type: 'Layer',
          id: attributesToUpdate.renderingLayer
        }
      };
    }
    if (attributesToUpdate.selectionLayerId) {
      relationships.selectionLayer = {
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
