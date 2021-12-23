
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

class FeatureTypeRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/featuretypes/', 'WFS-Feature Types');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText,
      sort: 'title'
      // 'filter[Featuretypes]': 'title'  //TODO
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }
    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      attributes: {},
      pagination: {
        next: res.data.links.next
      }
    }));
  }

  async autocompleteInitialValue (id:string): Promise<any> {
    const client = await JsonApiRepo.getClientInstance();

    const res = await client['retrieve' + this.resourcePath + '{id}/'](
      id,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType }
      }
    );
    return {
      value: res.data.data.id,
      text: res.data.data.attributes.title,
      attributes: res.data.data.attributes,
      pagination: {
        next: undefined
      }
    };
  }
}

export default FeatureTypeRepo;
