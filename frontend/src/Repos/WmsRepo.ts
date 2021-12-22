import JsonApiRepo from './JsonApiRepo';

class WebMapServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wms/', 'Darstellungsdienste (WMS)');
  }
}

export default WebMapServiceRepo;
