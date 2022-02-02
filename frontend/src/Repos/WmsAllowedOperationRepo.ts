import JsonApiRepo, { JsonApiResponse, QueryParams } from './JsonApiRepo';


class WmsAllowedOperationRepo extends JsonApiRepo {

  readonly wmsId: string;

  constructor (wmsId: string) {
    super('/api/v1/registry/wms/{parent_lookup_secured_service}/allowed-wms-operations/', 'Regeln');
    this.wmsId = wmsId;
  }

  async findAll (queryParams?: QueryParams): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
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
    return await client['List' + this.resourcePath](this.wmsId, jsonApiParams);
  }

}

export default WmsAllowedOperationRepo;
