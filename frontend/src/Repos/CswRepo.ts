import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';


export interface OgcServiceCreate {
  getCapabilitiesUrl: string;
  owner: string;
}

class CatalogueServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/csw/', ' (CSW)');
  }

  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      getCapabilitiesUrl: create.getCapabilitiesUrl,
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
