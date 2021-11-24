import OpenApiRepo from './OpenApiRepo';

export class WebMapServiceRepo extends OpenApiRepo<any> {
  constructor () {
    super('/api/v1/registry/wms/');
  }
}

export default WebMapServiceRepo;
