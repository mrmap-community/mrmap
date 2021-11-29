import { SearchFieldData } from '../Components/Shared/FormFields/SelectAutocompleteFormField/SelectAutocompleteFormField';
import JsonApiRepo from './JsonApiRepo';

export class OrganizationRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/users/organizations/');
  }

  async autocomplete (searchText: string | undefined): Promise<SearchFieldData[]> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'fields[Organization]': 'name'
    };
    if (searchText) {
      jsonApiParams['filter[name.icontains]'] = searchText;
    }
    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({ value: o.id, text: o.attributes.name }));
  }
}

export default OrganizationRepo;
