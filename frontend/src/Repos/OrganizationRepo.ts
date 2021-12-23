import { SearchFieldData } from '../Components/Shared/FormFields/SelectAutocompleteFormField/SelectAutocompleteFormField';
import JsonApiRepo from './JsonApiRepo';

class OrganizationRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/accounts/organizations/', 'Organisationen');
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
