
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

export class DatasetMetadataRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/dataset-metadata/', 'Metadatensätze');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[search]': searchText, // TODO: maybe add the possibility to search for the title
      sort: 'title'
      // 'filter[Layer]': 'title'
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[search]'];
    }

    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      pagination: {
        next: res.data.links.next
      },
      attributes: {
        associatedLayers: o.relationships.self_pointing_layers.data.map((dt:any) => dt.id)
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

export default DatasetMetadataRepo;
