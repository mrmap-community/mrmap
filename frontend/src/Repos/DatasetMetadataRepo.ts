
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse, QueryParams } from './JsonApiRepo';

class DatasetMetadataRepo extends JsonApiRepo {
  constructor () {
    super('DatasetMetadata');
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

    const res = await client['List' + this.resourceType](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      pagination: {
        next: res.data.links.next
      },
      attributes: {
        associatedLayers: o.relationships.selfPointingLayers.data.map((dt:any) => dt.id)
      }
    }));
  }

  async autocompleteInitialValue (id:string): Promise<any> {
    const client = await JsonApiRepo.getClientInstance();

    const res = await client['get' + this.resourceType](
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

  /**
   * @description overides the default findAll to add the include parameter
   * @param queryParams 
   * @returns 
   */
  async findAll (queryParams?: QueryParams): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    // TODO why does Parameters<UnknownParamsObject> not work?
    let jsonApiParams: any;
    if (queryParams) {
      jsonApiParams = {
        include: 'selfPointingLayers',
        //'fields[DatasetMetadata]': 'title,abstract,selfPointingLayers',
        //'fields[Layer]': 'title,name',
        'page[number]': queryParams.page,
        'page[size]': queryParams.pageSize,
        ...queryParams.filters
      };
      if (queryParams.ordering) {
        jsonApiParams.sort = queryParams.ordering;
      }
    }
    const res = await client['list' + this.resourceType](jsonApiParams);
    return res;

  }
}

export default DatasetMetadataRepo;
