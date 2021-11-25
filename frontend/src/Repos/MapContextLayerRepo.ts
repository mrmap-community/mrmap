import { RightCircleFilled } from '@ant-design/icons';

import OpenApiRepo from './OpenApiRepo';

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

  async create (create: MapContextLayerCreate): Promise<any> {
    const attributes:any = {
      name: create.name,
      title: create.title,
      lft: create.lft,
      rght: create.rght,
      tree_id: create.tree, //eslint-disable-line
      dataset_metadata_id: create.datasetMetadata, //eslint-disable-line
      rendering_layer_id: create.renderingLayer, //eslint-disable-line
      parent_id: create.parent, //eslint-disable-line
      layer_scale_max: create.layerScaleMax, //eslint-disable-line
      layer_scale_min: create.layerScaleMin, //eslint-disable-line
      layer_style_id: create.layerStyleId, //eslint-disable-line
      selection_layer_id: create.selectionLayerId //eslint-disable-line
    };
    if (create.title) {
      attributes.title = create.title;
    }
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
    return this.add('MapContextLayer', attributes, relationships);
  }
}

export default MapContextLayerRepo;
