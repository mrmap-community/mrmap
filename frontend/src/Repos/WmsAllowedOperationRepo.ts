import Cookies from 'js-cookie';
import JsonApiRepo, { JsonApiResponse, QueryParams } from './JsonApiRepo';

class WmsAllowedOperationRepo extends JsonApiRepo {

  readonly wmsId: string;

  constructor (wmsId: string) {
    super('/api/v1/registry/wms/{parent_lookup_secured_service}/allowed-wms-operations/', 'Zugriffsregeln');
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

  async delete (id: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const params = [
      {
        in: 'path',
        name: 'parent_lookup_secured_service',
        value: this.wmsId,
      },
      {
        in: 'path',
        name: 'id',
        value: id,
      },      
      {
        in: 'header',
        name: 'X-CSRFToken',
        value: Cookies.get('csrftoken') || ''
      }
    ];    
    return await client['destroy' + this.resourcePath + '{id}/'](params);
  }
}

export default WmsAllowedOperationRepo;
