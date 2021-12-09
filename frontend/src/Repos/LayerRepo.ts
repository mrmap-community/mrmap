
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

export class LayerRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/layers/');
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

  async getFromIdArray (idList: string[]): Promise<JsonApiResponse[]> {
    const client = await JsonApiRepo.getClientInstance();
    const layerResponses: JsonApiResponse[] = [];
    idList.forEach(async (id:string) => {
      const res = await client['retrieve' + this.resourcePath + '{id}/'](id, {}, {
        headers: { 'Content-Type': JsonApiMimeType }
      });
      const dataToAdd = {
        value: res.data.data.id,
        text: res.data.data.attributes.title,
        attributes: {
          scaleMin: res.data.data.attributes.scale_min,
          scaleMax: res.data.data.attributes.scale_max,
          style: res.data.data.attributes.style
        }
      };
      // @ts-ignore
      layerResponses.push(dataToAdd);
    });
    return layerResponses;
  }
}

export default LayerRepo;
