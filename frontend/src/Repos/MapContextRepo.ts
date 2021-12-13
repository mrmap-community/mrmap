
import { MPTTJsonApiTreeNodeType } from '../Components/Shared/FormFields/TreeFormField/TreeFormField';
import JsonApiRepo, { JsonApiMimeType, JsonApiPrimaryData, JsonApiResponse } from './JsonApiRepo';

export interface MapContextCreate {
    title: string;
    abstract?: string;
    ownerOrganizationId: string;
}

interface MapContextWithLayersResponseType {
  mapContext: JsonApiPrimaryData,
  mapContextLayers: MPTTJsonApiTreeNodeType[]
}

export class MapContextRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/mapcontexts/', 'Karten');
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
      owner: { // eslint-disable-line
        data: {
          type: 'MapContext',
          id: create.ownerOrganizationId
        }
      }
    };
    return this.add('MapContext', attributes, relationships);
  }

  async getMapContextWithLayers (mapContextId: string): Promise<MapContextWithLayersResponseType> {
    const client = await JsonApiRepo.getClientInstance();
    const res = await client['retrieve' + this.resourcePath + '{id}/'](
      mapContextId,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType },
        params: { include: 'map_context_layers' }
      }
    );
    return {
      mapContext: res.data.data,
      mapContextLayers: res.data.included
    };
  }
}

export default MapContextRepo;
