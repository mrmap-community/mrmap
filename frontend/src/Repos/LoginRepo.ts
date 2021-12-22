import JsonApiRepo, { JsonApiResponse } from './JsonApiRepo';

export interface Login {
    username: string;  // eslint-disable-line
    password: string; // eslint-disable-line
}

class LoginRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/accounts/login/', '');
  }

  async login (obtain: Login): Promise<JsonApiResponse> {
    const attributes = {
      username: obtain.username, // eslint-disable-line
      password: obtain.password
    };
    return this.add('Login', attributes, {});
  }
}

export default LoginRepo;
