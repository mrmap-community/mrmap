import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export class LogoutRepo extends OpenApiRepo {
    constructor () {
      super('/api/v1/users/logout/');
    }
  
    async logout (): Promise<JsonApiResponse> {
  
      return this.add('Logout', {}, {});
    }
  
  }
  
  export default LogoutRepo;
  