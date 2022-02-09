
import { MPTTJsonApiTreeNodeType } from '../Components/Shared/TreeManager/TreeManagerTypes';

import JsonApiRepo, { JsonApiMimeType, JsonApiPrimaryData, JsonApiResponse } from './JsonApiRepo';


export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

interface MapContextWithLayersResponseType {
  mapContext: JsonApiPrimaryData,
  mapContextLayers: MPTTJsonApiTreeNodeType[]
}

class MapContextRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontexts/', 'Karten');
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

  async getMapContextWithLayers (mapContextId: string): Promise<MapContextWithLayersResponseType> {
    const client = await JsonApiRepo.getClientInstance();
    const res = await client['retrieve' + this.resourcePath + '{id}/'](
      mapContextId,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType },
        params: { include: 'mapContextLayers' }
      }
    );
    return {
      mapContext: res.data.data,
      mapContextLayers: res.data.included
    };
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
