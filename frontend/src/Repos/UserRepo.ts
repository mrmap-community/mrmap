
import OpenApiRepo from './OpenApiRepo';

export class UserRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/users/users/');
  }
}

export default UserRepo;
