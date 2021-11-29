import JsonApiRepo from './JsonApiRepo';

export class WebMapServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wms/');
  }
}

export default WebMapServiceRepo;
