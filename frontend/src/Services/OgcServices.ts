import OpenAPIService from './OpenAPIService';

export interface OgcService {
    type: string;
    id: string;
    links: any;
    attributes: any;
    relationships: any;
}

export interface OgcServiceCreate {

    get_capabilities_url: string; // eslint-disable-line
    owned_by_org: string; // eslint-disable-line
}

export interface JsonApiResponse<T> {
    data: T[] | T;
    errors: any;
    meta: any;
}

interface QueryParams {
    page: number;
    pageSize: number;
    ordering: string;
    filters: any;
}

export class OgcServices {
  async getSchema (): Promise<any> {
    const client = await OpenAPIService.getClientInstance();
    const op = client.api.getOperation('List/api/v1/registry/wms/');
    if (!op) {
      return [];
    }
    const response: any = op.responses[200];
    if (!response) {
      return [];
    }
    const mimeType = response.content['application/vnd.api+json'];
    if (!mimeType) {
      return [];
    }
    return mimeType.schema;
  }

  async findAll (queryParams?: QueryParams): Promise<JsonApiResponse<OgcService>> {
    const client = await OpenAPIService.getClientInstance();
    // TODO why does Parameters<UnknownParamsObject> not work?
    let jsonApiParams: any;
    if (queryParams) {
      jsonApiParams = {
        'page[number]': queryParams.page,
        'page[size]': queryParams.pageSize,
        ...queryParams.filters
      };
      // TODO why can a string occur here?
      if (queryParams.ordering && queryParams.ordering !== 'undefined') {
        jsonApiParams.ordering = queryParams.ordering;
      }
    }
    const res = await client['List/api/v1/registry/wms/'](jsonApiParams);
    return res.data;
  }

  async delete (id: string): Promise<void> {
    const client = await OpenAPIService.getClientInstance();
    await client['destroy/api/v1/registry/ogcservices/{id}/'](id, {}, {
      headers: { 'Content-Type': 'application/vnd.api+json' }
    });
  }

  async create (create: OgcServiceCreate): Promise<any> {
    const client = await OpenAPIService.getClientInstance();
    return await client['create/api/v1/registry/ogcservices/'](undefined, {
      data: {
        type: 'OgcService',
        attributes: {
          get_capabilities_url: create.get_capabilities_url // eslint-disable-line
        },
        relationships: {
          // eslint-disable-next-line
          owned_by_org: {  
            data: {
              type: 'OgcService',
              id: create.owned_by_org
            }
          }
        }
      }
    }, { headers: { 'Content-Type': 'application/vnd.api+json' } });
  }
}

export default OgcServices;
