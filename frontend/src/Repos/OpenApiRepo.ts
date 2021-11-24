import OpenAPIClientAxios, { OpenAPIClient } from 'openapi-client-axios';

export const JsonApiMimeType = 'application/vnd.api+json';

export interface JsonApiResponse<T> {
    data: JsonApiObject<T>[] | JsonApiObject<T>;
    errors: any;
    meta: any;
}

export interface JsonApiObject<T> {
    type: string;
    id: string;
    links: any;
    // TODO add type info for attributes
    attributes: any;
    relationships: any;
}

export interface QueryParams {
    page: number;
    pageSize: number;
    ordering: string;
    filters: any;
}

export class OpenApiRepo<T> {
    private static apiInstance: OpenAPIClientAxios;

    private static clientInstance: OpenAPIClient;

    protected readonly resourcePath: string;

    constructor (resourcePath: string) {
      this.resourcePath = resourcePath;
    }

    static async getClientInstance () {
      if (!this.clientInstance) {
        this.clientInstance = await (await this.getApiInstance()).getClient();
      }
      return this.clientInstance;
    }

    static async getApiInstance () {
      if (!this.apiInstance) {
        if (process.env.REACT_APP_REST_API_SCHEMA_URL === undefined) {
          throw new Error('Environment variable REACT_APP_REST_API_SCHEMA_URL is undefined.');
        }
        if (process.env.REACT_APP_REST_API_BASE_URL === undefined) {
          throw new Error('Environment variable REACT_APP_REST_API_BASE_URL is undefined.');
        }
        this.apiInstance = new OpenAPIClientAxios({
          definition: process.env.REACT_APP_REST_API_SCHEMA_URL,
          axiosConfigDefaults: {
            baseURL: process.env.REACT_APP_REST_API_BASE_URL
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

    async getSchema (): Promise<any> {
      const client = await OpenApiRepo.getClientInstance();
      const op = client.api.getOperation('List' + this.resourcePath);
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

    async findAll (queryParams?: QueryParams): Promise<JsonApiResponse<T>> {
      const client = await OpenApiRepo.getClientInstance();
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
      const res = await client['List' + this.resourcePath](jsonApiParams);
      return res.data;
    }

    async delete (id: string): Promise<void> {
      const client = await OpenApiRepo.getClientInstance();
      await client['destroy' + this.resourcePath + '{id}/'](id, {}, {
        headers: { 'Content-Type': JsonApiMimeType }
      });
    }

    async add (type: string, attributes: any, relationships: any): Promise<any> {
      const client = await OpenApiRepo.getClientInstance();
      return await client['create' + this.resourcePath](undefined, {
        data: {
          type: type,
          attributes: {
            ...attributes
          },
          relationships: {
            ...relationships
          }
        }
      }, { headers: { 'Content-Type': JsonApiMimeType } });
    }
}

export default OpenApiRepo;
