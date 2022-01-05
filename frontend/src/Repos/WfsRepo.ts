import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export interface OgcServiceCreate {
  get_capabilities_url: string;  // eslint-disable-line
  owner: string; // eslint-disable-line
  collect_metadata_records: boolean; // eslint-disable-line
}

class WebFeatureServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wfs/', 'Downloaddienste (WFS)');
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
    return this.add('WebFeatureService', attributes, relationships);
  }
}

export default WebFeatureServiceRepo;
