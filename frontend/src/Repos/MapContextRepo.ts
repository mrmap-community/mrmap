import JsonApiRepo, { JsonApiMimeType, JsonApiPrimaryData, JsonApiResponse } from './JsonApiRepo';

export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

export class MapContextRepo extends JsonApiRepo {
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

  async getMapContextLayerFromMapContextId (mapContextId: string): Promise<JsonApiPrimaryData[]> {
    const client = await JsonApiRepo.getClientInstance();
    const res = await client['List' + this.resourcePath + '{parent_lookup_map_context}/mapcontextlayers/'](
      mapContextId,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType }
      }
    );
    return res.data.data;
  }
}

export default MapContextRepo;
