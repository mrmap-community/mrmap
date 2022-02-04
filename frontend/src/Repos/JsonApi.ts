import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export async function operation (
  operationId: string, 
  params?: any, 
  data?: any, 
  config?: any
): Promise<JsonApiResponse> {
  const client = await JsonApiRepo.getClientInstance();
  return await client[operationId](params, data, config);
}
