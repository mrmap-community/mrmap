import OpenApiRepo from './OpenApiRepo';

export interface TokenRepoObtain {
    username: string;  // eslint-disable-line
    password: string; // eslint-disable-line
}

export class TokenObtainRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/users/token/');
  }

  async obtain (obtain: TokenRepoObtain): Promise<any> {
    const attributes = {
      username: obtain.username, // eslint-disable-line
      password: obtain.password
    };
    return this.add('TokenObtainPairView', attributes, {});
  }
}

export default TokenObtainRepo;
