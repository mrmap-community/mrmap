import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export class OrganizationRepo extends OpenApiRepo {
  constructor() {
    super('/api/v1/users/organizations/');
  }

  async autocomplete(searchText: string): Promise<JsonApiResponse> {
    const client = await OpenApiRepo.getClientInstance();
    let jsonApiParams: any = {
      'filter[name.icontains]': searchText,
      'fields[Organization]': 'name'
    }
    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({ id: o.id, value: o.attributes.name }));
  }

}

export default OrganizationRepo;
