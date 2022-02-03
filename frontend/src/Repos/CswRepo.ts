import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';


export interface OgcServiceCreate {
  get_capabilities_url: string;  // eslint-disable-line
  owner: string; // eslint-disable-line
}

class CatalogueServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/csw/', ' (CSW)');
  }

  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      get_capabilities_url: create.get_capabilities_url, // eslint-disable-line
    };
    const relationships = {
      owner: { // eslint-disable-line
        data: {
          type: 'Organization',
          id: create.owner
        }
      }
    };
    return this.add('CatalougeService', attributes, relationships);
  }


}

export default CatalogueServiceRepo;
