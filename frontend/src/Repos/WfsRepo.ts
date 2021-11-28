import OpenApiRepo from './OpenApiRepo';

export class WebFeatureServiceRepo extends OpenApiRepo {
  constructor () {
    super('/api/v1/registry/wfs/');
  }
}

export default WebFeatureServiceRepo;
