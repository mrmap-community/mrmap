import OpenAPIClientAxios from 'openapi-client-axios';


/**
 * Collects the data of a paginated JSON:API response as a single JSON:API response structure.
 *
 * @param jsonApiResponse response that may contain a next link
 *
 * @throws {Error} if an error collecting the response pages occured
 */
// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
export async function unpage (jsonApiResponse: any, api: OpenAPIClientAxios): Promise<any> {
  const client = await api.getClient();
  const mergedResponse: any = jsonApiResponse;
  while (jsonApiResponse.data.links?.next) {
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


export function buildJsonApiPayload (
  type: string,
  id?: string | number,
  attributes?: Array<any>,
  relationships?: Array<any>): any {

  if (id){
    return {
      'data':{
        'type': type,
        'id': id,
        'attributes': { ...attributes },
        'relationships': { ...relationships }
      }
    };
  } else {
    return {
      'data':{
        'type': type,
        'attributes': { ...attributes },
        'relationships': { ...relationships }
      }
    };
  }

}

export function getQueryParams (api: OpenAPIClientAxios, operationId: string): any {
  const op = api.getOperation(operationId);
  if (!op) {
    return [];
  }
  const params:any = {};
  op.parameters?.forEach((element: any) => {
    params[element.name] = element;
  });
  return params;
}

