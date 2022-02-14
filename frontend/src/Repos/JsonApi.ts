import { message } from 'antd';
import Cookies from 'js-cookie';
import JsonApiRepo, { JsonApiMimeType } from './JsonApiRepo';

/**
 * Performs a JSON:API create or partial-update operation against the backend.
 * 
 * See the {@link https://www.npmjs.com/package/openapi-client-axios|openapi-client-axios README}
 * for details on the structure of the 'params' parameter.
 *
 * @param operationId operation id from the OpenAPI schema, e.g. 'create/api/v1/registry/wms/'
 * @param attributes attributes
 * @param relationships relationships
 * @param params optional query, header, path and cookie parameters, see above
 * @param id optional id, if present, this is an update operation
 * @returns JSON:API response from backend
 * 
 * @throws {Error} if an error performing the operation was detected
 */
export async function createOrUpdate (
  operationId: string,
  type: string,
  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
  attributes: any,
  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types  
  relationships: any,
  params?: any[],
  id?:string  
): Promise<any> {
  const data: any = {
    data: {
      type: type,      
      attributes: {
        ...attributes
      },
      relationships: {
        ...relationships
      }
    }
  };
  if (id) {
    data.data.id = id;
  }
  const paramsWithHeaders = [{
    in: 'header',
    name: 'Content-Type',
    value: JsonApiMimeType
  },
  {
    in: 'header',
    name: 'X-CSRFToken',
    value: Cookies.get('csrftoken')
  },
  ...params ? params : []
  ];
  return operation(operationId, paramsWithHeaders, data);
}

/**
 * Performs a JSON:API operation based on the operation id from the backend's OpenAPI schema.
 * 
 * See the {@link https://www.npmjs.com/package/openapi-client-axios|openapi-client-axios README}
 * for details on the structure of the 'params' parameter.
 * 
 * @param operationId operation id from the OpenAPI schema, e.g. 'List/api/v1/registry/wms/'
 * @param params optional query, header, path and cookie parameters, see above
 * @param data optional request payload
 * @returns JSON:API response from backend
 * 
 * @throws {Error} if an error performing the operation was detected
 */
export async function operation (
  operationId: string, 
  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
  params?: any,
  // eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
  data?: any,
): Promise<any> {
  const client = await JsonApiRepo.getClientInstance();
  const op = client[operationId];
  if (! op || !(typeof op === 'function')) {
    const msg = `Frontend/backend mismatch: OpenAPI schema does not define operation ${operationId}`;
    console.error(msg);
    message.error(msg, 0);
    throw new Error(msg);
  }
  return performJsonApiCallAndReportErrors( async () => {
    return op(params, data);
  });
}

/**
 * Collects the data of a paginated JSON:API response as a single JSON:API response structure.
 * 
 * @param jsonApiResponse response that may contain a next link
 * 
 * @throws {Error} if an error collecting the response pages occured
 */
// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
export async function unpage (jsonApiResponse: any): Promise<any> {
  const client = await JsonApiRepo.getClientInstance();
  const mergedResponse: any = jsonApiResponse;
  while (jsonApiResponse.data.links.next) {
    const next = jsonApiResponse.data.links.next;
    jsonApiResponse = await client.get(next);
    mergedResponse.data.data = mergedResponse.data.data.concat(jsonApiResponse.data.data);
  }
  if (mergedResponse.data.links) {
    mergedResponse.data.links.first = null;
    mergedResponse.data.links.last = null;
    mergedResponse.data.links.next = null;
    mergedResponse.data.links.prev = null;
  }
  return mergedResponse;
}

async function performJsonApiCallAndReportErrors ( fn: () => Promise<any>) : Promise<any> {
  try {
    const response = await fn();
    return response;
  } catch (err) {
    console.error('Backend operation failed', err);
    message.error('Backend operation failed (see console for details)', 0);    
    throw err;
  }
}
