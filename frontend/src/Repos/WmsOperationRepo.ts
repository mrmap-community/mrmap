import JsonApiRepo from './JsonApiRepo';

class WmsOperationRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/security/wms-operations/', 'WMS-Operationen');
  }
}

export default WmsOperationRepo;
