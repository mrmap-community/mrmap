import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';


export interface OgcServiceCreate {
  getCapabilitiesUrl: string;
  owner: string;
  collectMetadataRecords: boolean;
}

class WebMapServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wms/', 'Darstellungsdienste (WMS)');
  }

  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      getCapabilitiesUrl: create.getCapabilitiesUrl,
      collectMetadataRecords: create.collectMetadataRecords 
    };
    const relationships = {
      owner: {
        data: {
          type: 'Organization',
          id: create.owner
        }
      }
    };
    return this.add('WebMapService', attributes, relationships);
  }

  async get (id: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const params = [
      {
        in: 'path',
        name: 'id',
        value: id,
      },
      {
        in: 'header',
        name: 'Content-Type',
        value: 'JsonApiMimeType',
      },
      {
        in: 'query',
        name: 'include',
        value: 'operationUrls'
      }
    ];    
    return await client['retrieve' + this.resourcePath + '{id}/'](params);
  }

}

export default WebMapServiceRepo;
