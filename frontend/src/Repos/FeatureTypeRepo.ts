
import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export class FeatureTypeRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/featuretypes/');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText
      // 'filter[Featuretypes]': 'title'  //TODO
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }
    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({ value: o.id, text: o.attributes.title }));
  }
}

export default FeatureTypeRepo;