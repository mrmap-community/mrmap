
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

class MapContextRepo extends JsonApiRepo {
  constructor () {
    super('MapContext');
  }

  async create (create: MapContextCreate): Promise<JsonApiResponse> {
    const attributes:any = {
      title: create.title,
      abstract: create.abstract
    };

    const relationships = {
      owner: { // eslint-disable-line
        data: {
          type: 'MapContext',
          id: create.ownerOrganizationId
        }
      }
    };
    return this.add('MapContext', attributes, relationships);
  }

  async getMapContextWithLayers (mapContextId: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const res = await client['get' + this.resourceType](
      mapContextId,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType },
        params: { include: 'mapContextLayers.renderingLayer.service.operationUrls' }
      }
    );
    return res;
  }

  async update (mapContextId:string, attributesToUpdate: MapContextCreate): Promise<JsonApiResponse> {
    const attributes:any = {
      title: attributesToUpdate.title,
      abstract: attributesToUpdate.abstract
    };

    const relationships:any = {};

    if (attributesToUpdate.ownerOrganizationId) {
      relationships.owner = {
        data: {
          type: 'MapContext',
          id: attributesToUpdate.ownerOrganizationId
        }
      };
    }

    return this.partialUpdate(mapContextId, 'MapContext', attributes, relationships);
  }

}

export default MapContextRepo;
