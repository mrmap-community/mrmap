import JsonApiRepo from './JsonApiRepo';

class UserRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/accounts/users/', 'Benutzer');
  }
}

export default UserRepo;
