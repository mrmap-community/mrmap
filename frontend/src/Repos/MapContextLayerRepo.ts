import { RightCircleFilled } from '@ant-design/icons';
import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

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
}

export class MapContextLayerRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontextlayers/');
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
}

export default MapContextLayerRepo;
