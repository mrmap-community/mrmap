
import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export class LayerRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/layers/');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await OpenApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText
      // 'fields[Layer]': 'scale_max, scale_min, title'  // TODO: not working. Grab all for now
    };
    if (!searchText) {
      delete jsonApiParams['filter[title.icontains]'];
    }

    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      attributes: {
        scaleMin: o.attributes.scale_min,
        scaleMax: o.attributes.scale_max,
        style: '' // o.attributes.style,  TODO: not available  at the moment
      }
    }));
  }
}

export default LayerRepo;
