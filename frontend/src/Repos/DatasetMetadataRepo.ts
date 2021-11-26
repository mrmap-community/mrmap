
import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export class DatasetMetadataRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/dataset-metadata/');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await OpenApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText
      // 'filter[Layer]': 'title'
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }

    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({ value: o.id, text: o.attributes.title }));
  }
}

export default DatasetMetadataRepo;
