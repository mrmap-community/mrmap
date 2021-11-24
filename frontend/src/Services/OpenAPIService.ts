import OpenAPIClientAxios, { OpenAPIClient } from 'openapi-client-axios';

export class OpenAPIService {
    private static apiInstance: OpenAPIClientAxios;

    private static clientInstance: OpenAPIClient;

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
}

export default OpenAPIService;
