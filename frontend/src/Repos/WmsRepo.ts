import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';


export interface OgcServiceCreate {
  get_capabilities_url: string;  // eslint-disable-line
  owner: string; // eslint-disable-line
  collect_metadata_records: boolean; // eslint-disable-line
}

class WebMapServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wms/', 'Darstellungsdienste (WMS)');
  }

  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      get_capabilities_url: create.get_capabilities_url, // eslint-disable-line
      collect_metadata_records: create.collect_metadata_records // eslint-disable-line
    };
    const relationships = {
      owner: { // eslint-disable-line
        data: {
          type: 'Organization',
          id: create.owner
        }
      }
    };
    return this.add('WebMapService', attributes, relationships);
  }

  async getAllLayers (id: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const params = [
      {
        in: 'path',
        name: 'parent_lookup_service',
        value: id,
      },
      {
        in: 'query',
        name: 'page[size]',
        value: 1000,
      }
    ];
    return await client['List' + this.resourcePath + '{parent_lookup_service}/layers/'](params);
  }

}

export default WebMapServiceRepo;
