import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export class LogoutRepo extends JsonApiRepo {
    constructor () {
      super('/api/v1/users/logout/');
    }
  
    async logout (): Promise<JsonApiResponse> {
  
      return this.add('Logout', {}, {});
    }
  
  }
  
  export default LogoutRepo;
  