import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

class LogoutRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/accounts/logout/', '');
  }

  async logout (): Promise<JsonApiResponse> {
    return this.add('Logout', {}, {});
  }
}

export default LogoutRepo;
