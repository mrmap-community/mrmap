import JsonApiRepo from './JsonApiRepo';

class UserRepo extends JsonApiRepo {
  constructor () {
    super('User');
  }
}

export default UserRepo;
