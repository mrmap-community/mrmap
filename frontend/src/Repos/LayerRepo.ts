
import Polygon from 'ol/geom/Polygon';
import JsonApiRepo, { JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

const getServiceType = (url:string): string => {
  if(url) {
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
    } else {
      return '';
    }

  } else {
    return '';
  }
};

const getServiceUrl = (includedServices: any[], operation:string) => {
  const getMapService = includedServices.find(service => service.attributes.operation === operation);
  if(getMapService) {

    return getMapService.attributes.url;
  }
};
class LayerRepo extends JsonApiRepo {
  constructor () {
    super('Layer');
  }

  async autocomplete (searchText: string): Promise<JsonApiResponse> {
    const client = await JsonApiRepo.getClientInstance();
    const jsonApiParams: any = {
      'filter[title.icontains]': searchText,
      sort: 'title',
      include: 'service.operationUrls'
      // 'fields[Layer]': 'scaleMax, scaleMin, title'  // TODO: not working. Grab all for now
    };
    if (!searchText) {
      // to avoid error when string is empty
      delete jsonApiParams['filter[title.icontains]'];
    }

    const res = await client['list' + this.resourceType](jsonApiParams);
    return res.data.data.map((o: any) => { 
      return ({
        value: o.id,
        text: o.attributes.title,
        attributes: {
          ...o.attributes,
          WMSParams: {
            layer: o.attributes.identifier,
            url: res.data.included && res.data.included.length > 0 && getServiceUrl(res.data.included, 'GetMap'),
            version: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.version,
            serviceType: res.data.included && res.data.included.length > 0 && 
             getServiceType(getServiceUrl(res.data.included, 'GetMap'))
          },
        },
        pagination: {
          next: res.data.links.next
        }
      });
    });
  }

  async autocompleteInitialValue (id:string): Promise<any> {
    const client = await JsonApiRepo.getClientInstance();

    const res = await client['get' + this.resourceType](
      id,
      {},
      {
        headers: { 'Content-Type': JsonApiMimeType },
        params: { include: 'service.operationUrls' }
      }
    );

    let styles;
    let included;
    let extent = null;
    if(res.data.data?.attributes?.bboxLatLon?.coordinates) {
      extent = new Polygon(res.data.data.attributes.bboxLatLon.coordinates).getExtent();
    }
    if(res.data.data?.relationships.styles.data?.length > 0) {
      styles = res.data.data?.relationships.styles.data.map((s:any) => s.id);
    }
    if(res.data.included) {
      included = res.data.included.find((inc:any) => inc.attributes.operation === 'GetLegendGraphic');
    }

    return {
      value: res.data.data.id,
      text: res.data.data.attributes.title,
      attributes: {
        ...res.data.data.attributes,
        id: res.data.data.id,
        scaleMin: res.data.data.attributes.scaleMin,
        scaleMax: res.data.data.attributes.scaleMax,
        style: styles,
        WMSParams: {
          bbox: extent,
          layer: res.data.data.attributes.identifier,
          url: res.data.included && res.data.included.length > 0  && getServiceUrl(res.data.included, 'GetMap'),
          version: res.data.included && res.data.included.length > 0 && res.data.included[0].attributes.version,
          serviceType: res.data.included && res.data.included.length > 0 && 
            getServiceType(getServiceUrl(res.data.included, 'GetMap')),
          legendUrl: included ? included.attributes.url : ''
        },
      },
      pagination: {
        next: undefined
      }
    };
  }
}

export default LayerRepo;
