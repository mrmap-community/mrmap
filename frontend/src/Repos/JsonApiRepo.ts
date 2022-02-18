import Cookies from 'js-cookie';
import OpenAPIClientAxios, { AxiosResponse, OpenAPIClient } from 'openapi-client-axios';

export const JsonApiMimeType = 'application/vnd.api+json';

export type JsonApiResponse = AxiosResponse<JsonApiDocument | null>

export interface JsonApiDocument {
    data?: JsonApiPrimaryData[] | JsonApiPrimaryData;
    // data?: JsonApiDocumentData; TODO: replace by this one
    errors?: JsonApiErrorObject;
    meta?: any;
    links?: any;
    included?: any;
}

export interface JsonApiErrorSource {
  pointer?: string;
  parameter?: string;
}

export interface JsonApiErrorObject {
  id: string;
  links: any; // TODO: add JsonApiLinkObject
  status: string;
  code: string;
  title: string;
  detail: string;
  source: JsonApiErrorSource;
}

// TODO: add and complete this one.
// export interface JsonApiDocumentData {
//   data: JsonApiPrimaryData[] | JsonApiPrimaryData;
// }
export interface JsonApiPrimaryData {
    type: string;
    id: string;  // TODO: only on patch needed (update)
    links: any; // TODO: add JsonApiLinkObject
    attributes: any;
    relationships: any;
}

export interface QueryParams {
    page: number;
    pageSize: number;
    ordering?: string;
    filters?: any;
}

export class BaseJsonApiRepo {
  protected static readonly REACT_APP_REST_API_BASE_URL = '/';

  protected static readonly REACT_APP_REST_API_SCHEMA_URL = '/api/schema/';

  protected static apiInstance: OpenAPIClientAxios;

  protected static clientInstance: OpenAPIClient;

  static async getClientInstance (): Promise<OpenAPIClient> {
    if (!this.clientInstance) {
      this.clientInstance = await (await this.getApiInstance()).getClient();
    }
    return this.clientInstance;
  }

  static async getApiInstance (): Promise<OpenAPIClientAxios> {
    if (!this.apiInstance) {
      this.apiInstance = new OpenAPIClientAxios({
        definition: BaseJsonApiRepo.REACT_APP_REST_API_SCHEMA_URL,
        axiosConfigDefaults: {
          baseURL: BaseJsonApiRepo.REACT_APP_REST_API_BASE_URL
        }
      });
      try {
        await this.apiInstance.init();
      } catch (err) {
        console.error(err);
      }
    }
    return this.apiInstance;
  }

}

class JsonApiRepo extends BaseJsonApiRepo {
   
    protected readonly resourceType: string;

    readonly displayName: string;

    constructor (resourceType: string) {
      super();
      this.resourceType = resourceType;
      // TODO: obtain it from the schema
      this.displayName = resourceType;
    }

    async getResourceSchema (): Promise<any> {
      const client = await JsonApiRepo.getClientInstance();
      // TODO: schema may differs on operations
      const op = client.api.getOperation('list' + this.resourceType);
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

    async getQueryParams (): Promise<any> {
      const client = await JsonApiRepo.getClientInstance();
      const op = client.api.getOperation('list' + this.resourceType);
      if (!op) {
        return [];
      }
      const params:any = {};
      op.parameters?.forEach((element: any) => {
        params[element.name] = element;
      });
      return params;
    }

    async findAll (queryParams?: QueryParams): Promise<JsonApiResponse> {
      const client = await JsonApiRepo.getClientInstance();
      // TODO why does Parameters<UnknownParamsObject> not work?
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
      return await client['list' + this.resourceType](jsonApiParams);
    }

    // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
    async create (create: any): Promise<JsonApiResponse> {
      throw new Error('This method is abstract');
    }

    async get (id: string): Promise<JsonApiResponse> {
      const client = await JsonApiRepo.getClientInstance();
      return await client['get' + this.resourceType](id, {}, {
        headers: { 'Content-Type': JsonApiMimeType }
      });
    }

    async delete (id: string): Promise<JsonApiResponse> {
      const client = await JsonApiRepo.getClientInstance();
      return await client['delete' + this.resourceType](id, {}, {
        headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') as string }
      });
    }

    // eslint-disable-next-line
    async add (type: string, attributes: any, relationships?: any): Promise<JsonApiResponse> {
      const client = await JsonApiRepo.getClientInstance();

      // TODO: make relationships optional
      return await client['create' + this.resourceType](undefined, {
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
        headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') as string },
      });
    }

    async partialUpdate (
      id: string,
      type: string,
      attributes: Record<string, unknown>,
      relationships?: Record<string, unknown>
    ): Promise<JsonApiResponse> {
      const client = await JsonApiRepo.getClientInstance();
      // TODO: make relationships optional
      return await client['update' + this.resourceType](id, {
        data: {
          type: type,
          id: id,
          attributes: {
            ...attributes
          },
          relationships: {
            ...relationships
          }
        }
      }, {
        headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') as string }
      });
    }
}

export default JsonApiRepo;
