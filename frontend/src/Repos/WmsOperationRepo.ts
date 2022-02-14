import JsonApiRepo from './JsonApiRepo';

class WmsOperationRepo extends JsonApiRepo {
  constructor () {
    super('tWebMapServiceOperation');
  }
}

export default WmsOperationRepo;
