import OpenApiRepo from './OpenApiRepo';

export interface MapContextLayerCreate {
    name: string;
    title?: string;
    mapContextId: string
    parentLayerId?: string;
}

export class MapContextLayerRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontextlayers/');
  }

  async create (create: MapContextLayerCreate): Promise<any> {
    const attributes:any = {
      name: create.name
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
