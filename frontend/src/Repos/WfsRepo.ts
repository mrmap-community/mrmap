import JsonApiRepo from './JsonApiRepo';

export class WebFeatureServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wfs/');
  }
}

export default WebFeatureServiceRepo;
