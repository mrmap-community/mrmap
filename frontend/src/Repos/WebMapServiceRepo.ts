import OpenApiRepo from './OpenApiRepo';

export class WebMapServiceRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/wms/');
  }
}

export default WebMapServiceRepo;
