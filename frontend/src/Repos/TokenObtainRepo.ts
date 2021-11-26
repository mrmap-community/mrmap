import OpenApiRepo, { JsonApiResponse } from './OpenApiRepo';

export interface TokenRepoObtain {
    username: string;  // eslint-disable-line
    password: string; // eslint-disable-line
}


export class TokenObtainRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/users/token/');
  }

  async obtain (obtain: TokenRepoObtain): Promise<JsonApiResponse> {
    const attributes = {
      username: obtain.username, // eslint-disable-line
      password: obtain.password
    };
    return this.add('Token', attributes, {});
  }
}

export default TokenObtainRepo;
