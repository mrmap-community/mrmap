import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export interface OgcServiceCreate {
    get_capabilities_url: string;  // eslint-disable-line
    owned_by_org: string; // eslint-disable-line
    collect_metadata_records: boolean; // eslint-disable-line
}

export class OgcServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/ogcservices/');
  }

  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      get_capabilities_url: create.get_capabilities_url, // eslint-disable-line
      collect_metadata_records: create.collect_metadata_records // eslint-disable-line
    };
    const relationships = {
      owned_by_org: { // eslint-disable-line
        data: {
          type: 'Organization',
          id: create.owned_by_org
        }
      }
    };
    return this.add('OgcService', attributes, relationships);
  }
}

export default OgcServiceRepo;
