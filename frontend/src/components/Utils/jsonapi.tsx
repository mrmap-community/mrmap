import type OpenAPIClientAxios from 'openapi-client-axios';
import type { AxiosResponse } from 'openapi-client-axios';

export const JsonApiMimeType = 'application/vnd.api+json';

export type JsonApiResponse = AxiosResponse<JsonApiDocument | null>;

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

export interface ResourceIdentifierObject {
  type: string;
  id: string | number;
  meta?: any;
}

export interface ResourceLinkage {
  links: any;
  data: null | ResourceIdentifierObject | ResourceIdentifierObject[];
  meta?: any;
}

// TODO: add and complete this one.
// export interface JsonApiDocumentData {
//   data: JsonApiPrimaryData[] | JsonApiPrimaryData;
// }
export interface JsonApiPrimaryData {
  type: string;
  id: string; // TODO: only on patch needed (update)
  links: any; // TODO: add JsonApiLinkObject
  attributes: any;
  relationships: Record<string, ResourceLinkage>;
}

export interface QueryParams {
  page: number;
  pageSize: number;
  ordering?: string;
  filters?: any;
}

/**
 * Collects the data of a paginated JSON:API response as a single JSON:API response structure.
 *
 * @param jsonApiResponse response that may contain a next link
 *
 * @throws {Error} if an error collecting the response pages occured
 */
// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
export async function unpage(jsonApiResponse: any, api: OpenAPIClientAxios): Promise<any> {
  const client = await api.getClient();
  const mergedResponse: any = jsonApiResponse;
  let current = jsonApiResponse;
  while (current.data.links?.next) {
    const next = jsonApiResponse.data.links.next;
    current = await client.get(next);
    mergedResponse.data.data = mergedResponse.data.data.concat(current.data.data);
  }
  if (mergedResponse.data.links) {
    mergedResponse.data.links.first = null;
    mergedResponse.data.links.last = null;
    mergedResponse.data.links.next = null;
    mergedResponse.data.links.prev = null;
  }
  return mergedResponse;
}

export function buildJsonApiPayload(
  type: string,
  id?: string | number,
  attributes?: any,
  relationships?: any[],
): any {
  if (id) {
    return {
      data: {
        type: type,
        id: id,
        attributes: { ...attributes },
        relationships: { ...relationships },
      },
    };
  } else {
    return {
      data: {
        type: type,
        attributes: { ...attributes },
        relationships: { ...relationships },
      },
    };
  }
}

export function getQueryParams(api: OpenAPIClientAxios, operationId: string): any {
  const op = api.getOperation(operationId);
  if (!op) {
    return [];
  }
  const params: any = {};
  op.parameters?.forEach((element: any) => {
    params[element.name] = element;
  });
  return params;
}
