import OpenAPIClientAxios from 'openapi-client-axios';



export function buildJsonApiPayload (type: string, attributes?: Array<any>, relationships?: Array<any>): any {
    
  return {
    'data':{
      'type': type,
      'attributes': { ...attributes },
      'relationships': { ...relationships }
    }
  };
    
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

