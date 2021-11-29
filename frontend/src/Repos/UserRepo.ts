
import JsonApiRepo from './JsonApiRepo';

export class UserRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/users/users/');
  }
}

export default UserRepo;
