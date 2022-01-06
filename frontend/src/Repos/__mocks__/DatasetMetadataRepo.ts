import OpenAPIClientAxios, { OpenAPIV3 } from 'openapi-client-axios';
import DatasetsJson from './data/DatasetMetadata.json';
// @ts-ignore
import OpenApiSpec from './openapi.json';

const api = new OpenAPIClientAxios({
  definition: OpenApiSpec as OpenAPIV3.Document
});
api.init();

const mock = jest.fn().mockImplementation(() => {
  return {
    getResourceSchema: () => {
      const op = api.getOperation('List/api/v1/registry/dataset-metadata/' );
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
    },
    getQueryParams: () => {
      return {};
    },
    findAll: () => {
      return DatasetsJson;
    },
  };
});

export default mock;
