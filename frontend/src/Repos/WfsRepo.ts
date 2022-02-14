import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export interface OgcServiceCreate {
  getCapabilitiesUrl: string;
  owner: string;
  collectMetadataRecords: boolean;
}

class WebFeatureServiceRepo extends JsonApiRepo {
  constructor () {
    super('WebFeatureService');
  }
  
  async create (create: OgcServiceCreate): Promise<JsonApiResponse> {
    const attributes = {
      getCapabilitiesUrl: create.getCapabilitiesUrl,
      collectMetadataRecords: create.collectMetadataRecords 
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
