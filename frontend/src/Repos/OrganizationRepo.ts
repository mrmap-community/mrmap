import { SearchFieldData } from '../Components/Shared/FormFields/SelectAutocompleteField/SelectAutocompleteField';
import JsonApiRepo from './JsonApiRepo';

class OrganizationRepo extends JsonApiRepo {
  constructor () {
    super('Organization');
  }

  async autocomplete (searchText: string | undefined): Promise<SearchFieldData[]> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'fields[Organization]': 'name'
    };
    if (searchText) {
      jsonApiParams['filter[name.icontains]'] = searchText;
    }
    const res = await client['list' + this.resourceType](jsonApiParams);
    return res.data.data.map((o: any) => ({ value: o.id, text: o.attributes.name }));
  }
}

export default OrganizationRepo;
