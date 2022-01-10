
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

const getServiceType = (url:string): string => {
  const rightUrl = new URL(url);
  if (rightUrl.pathname.includes('mapserv')) {
    return 'MAPSERVER';
  }
  if (rightUrl.pathname.includes('geoserver')) {
    return 'GEOSERVER';
  }
  if (rightUrl.pathname.includes('qgis')) {
    return 'QGIS';
  }
  if (rightUrl.pathname.includes('esri')) {
    return 'ESRI';
  }
  return '';
};
class LayerRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/registry/layers/', 'WMS-Ebenen');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText,
      sort: 'title',
      include: 'service.operation_urls'
      // 'fields[Layer]': 'scale_max, scale_min, title'  // TODO: not working. Grab all for now
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }

    const res = await client['List' + this.resourcePath](jsonApiParams);
    return res.data.data.map((o: any) => ({
      value: o.id,
      text: o.attributes.title,
      attributes: {
        ...o.attributes,
        WMSParams: {
          layer: o.attributes.identifier,
          url: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.service_url,
          version: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.version,
          serviceType: res.data.included && res.data.included.length > 0 && 
            getServiceType(res.data.included[0].attributes.service_url)
        },
      },
      pagination: {
        next: res.data.links.next
      }
    }));
  }

  async autocompleteInitialValue (id:string): Promise<any> {
    const client = await JsonApiRepo.getClientInstance();

    const res = await client['retrieve' + this.resourcePath + '{id}/'](
      id,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType },
        params: { include: 'service.operation_urls' }
      }
    );
    
    return {
      value: res.data.data.id,
      text: res.data.data.attributes.title,
      attributes: {
        ...res.data.data.attributes,
        id: res.data.data.id,
        scaleMin: res.data.data.attributes.scale_min,
        scaleMax: res.data.data.attributes.scale_max,
        style: '',
        WMSParams: {
          bbox: res.data.data.attributes.bbox_lat_lon.coordinates,
          layer: res.data.data.attributes.identifier,
          url: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.service_url,
          version: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.version,
          serviceType: res.data.included && res.data.included.length > 0 && 
            getServiceType(res.data.included[0].attributes.service_url)
        },
      },
      pagination: {
        next: undefined
      }
    };
  }
}

export default LayerRepo;
