import OpenAPIClientAxios from 'openapi-client-axios';

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

