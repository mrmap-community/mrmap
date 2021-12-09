import JsonApiRepo from './JsonApiRepo';

export class WebMapServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wms/', 'Darstellungsdienste (WMS)');
  }
}

export default WebMapServiceRepo;
