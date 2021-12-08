import JsonApiRepo from './JsonApiRepo';

export class WebFeatureServiceRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/wfs/', 'Downloaddienste (WFS)');
  }
}

export default WebFeatureServiceRepo;
