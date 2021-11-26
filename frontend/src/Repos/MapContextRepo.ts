import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

export class MapContextRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontexts/');
  }

  async create (create: MapContextCreate): Promise<JsonApiResponse> {
    const attributes:any = {
      title: create.title,
      abstract: create.abstract
    };
    if (create.abstract) {
      attributes.abstract = create.abstract;
    }
    const relationships = {
      owned_by_org: { // eslint-disable-line
        data: {
          type: 'MapContext',
          id: create.ownerOrganizationId
        }
      }
    };
    return this.add('MapContext', attributes, relationships);
  }
}

export default MapContextRepo;
