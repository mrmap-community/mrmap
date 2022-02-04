import Cookies from 'js-cookie';
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse, QueryParams } from './JsonApiRepo';

export interface WmsAllowedOperationCreate {
  description: string;
  allowedGroupIds: Array<string>;
  allowedOperationIds: Array<string>;
  securedLayerIds: Array<string>;
}

class WmsAllowedOperationRepo extends JsonApiRepo {

  readonly wmsId: string;

  constructor (wmsId: string) {
    super('/api/v1/registry/wms/{parent_lookup_secured_service}/allowed-wms-operations/', 'Zugriffsregeln');
    this.wmsId = wmsId;
  }

  async findAll (queryParams?: QueryParams): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    let jsonApiParams: any;
    if (queryParams) {
      jsonApiParams = {
        'page[number]': queryParams.page,
        'page[size]': queryParams.pageSize,
        ...queryParams.filters
      };
      if (queryParams.ordering) {
        jsonApiParams.sort = queryParams.ordering;
      }
    }
    return await client['List' + this.resourcePath](this.wmsId, jsonApiParams);
  }

  async add (type: string, attributes: any, relationships?: any): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    return await client['create' + this.resourcePath](this.wmsId, {
      data: {
        type: type,
        attributes: {
          ...attributes
        },
        relationships: {
          ...relationships
        }
      }
    }, {
      headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') },
    });
  }

  async delete (id: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const params = [
      {
        in: 'path',
        name: 'parent_lookup_secured_service',
        value: this.wmsId,
      },
      {
        in: 'path',
        name: 'id',
        value: id,
      },      
      {
        in: 'header',
        name: 'X-CSRFToken',
        value: Cookies.get('csrftoken') || ''
      }
    ];    
    return await client['destroy' + this.resourcePath + '{id}/'](params);
  }

  async create (create: WmsAllowedOperationCreate): Promise<JsonApiResponse> {
    const attributes = {
      description: create.description
    };
    const relationships = {
      'secured_service': {
        data: {
          type: 'WebMapService',
          id: this.wmsId
        }
      },
      'secured_layers': {
        data: create.securedLayerIds.map((id) => {
          return {
            type: 'Layer',
            id: id
          };
        })
      },
      'operations': {
        data: create.allowedOperationIds.map((id) => {
          return {
            type: 'WebMapServiceOperation',
            id: id
          };
        })
      },
      'allowed_groups': {
        data: create.allowedGroupIds.map((id) => {
          return {
            type: 'Group',
            id: id
          };
        })
      }      
    };
    return this.add('AllowedWebMapServiceOperation', attributes, relationships);
  }

}

export default WmsAllowedOperationRepo;