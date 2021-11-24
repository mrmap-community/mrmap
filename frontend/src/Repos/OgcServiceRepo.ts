import OpenApiRepo from './OpenApiRepo';

export interface OgcServiceCreate {
    get_capabilities_url: string;  // eslint-disable-line
    owned_by_org: string; // eslint-disable-line
}

export class OgcServiceRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/ogcservices/');
  }

  async create (create: OgcServiceCreate): Promise<any> {
    const attributes = {
      get_capabilities_url: create.get_capabilities_url // eslint-disable-line
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
