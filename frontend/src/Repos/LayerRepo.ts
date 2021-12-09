
import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export class LayerRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/layers/', 'WMS-Ebenen');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText
      // 'fields[Layer]': 'scale_max, scale_min, title'  // TODO: not working. Grab all for now
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }

    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      attributes: {
        scaleMin: o.attributes.scale_min,
        scaleMax: o.attributes.scale_max,
        style: o.attributes.style
      }
    }));
  }
}

export default LayerRepo;
