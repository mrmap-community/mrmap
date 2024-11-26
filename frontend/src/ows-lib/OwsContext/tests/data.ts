import { OWSResource } from '../types'


export const karteRpFeatures: OWSResource[] = [
  {
      "type": "Feature",
      "properties": {
          "title": "Karte RP",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilities",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=atkis1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ]
              }
          ],
          "folder": "/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesfläche",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesflaeche",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesflaeche&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Land 0",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=rlp_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=rlp_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/0/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Land 1",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=rlp_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=rlp_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/0/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Land 2",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=rlp_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=rlp_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/0/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Land 3",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=rlp_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=rlp_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/0/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Wald",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Wald&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald 0",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=wald_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=wald_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald 1",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=wald_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=wald_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald 2",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=wald_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=wald_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald 3",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=wald_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=wald_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wald 4",
          "updated": "2024-05-03T10:26:38.476Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=wald_04",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=wald_04&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/1/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Sonderkultur",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Sonderkultur&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=sonderkultur_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=sonderkultur_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=sonderkultur_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=sonderkultur_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=sonderkultur_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=sonderkultur_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=sonderkultur_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=sonderkultur_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonderkultur 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=sonderkultur_04",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=sonderkultur_04&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/2/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Ortslage",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Ortslage&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 00",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_000",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_000&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortslage 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ortslage_04",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ortslage_04&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Friedhof 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_friedhof_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_friedhof_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Friedhof",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_friedhof_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_friedhof_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/3/7"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Flughaefen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Flughaefen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Flughaefen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Flughafenflaeche",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=flughafen01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=flughafen01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/4/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Flughafengelaende",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=flughafen02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=flughafen02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/4/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrieflächen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Industrie",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Industrie&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrie 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=industrie_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=industrie_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrie 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=industrie_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=industrie_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrie 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=industrie_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=industrie_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrie 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=industrie_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=industrie_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Industrie 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=industrie_04",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=industrie_04&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Tagebau 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=tagebau_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=tagebau_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Tagebau 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=tagebau_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=tagebau_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/5/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Schummerung",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Schummerung",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Schummerung&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Schummerung",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=SchummerungRP",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ]
              }
          ],
          "folder": "/0/6/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Flüsse",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Fluesse",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Fluesse&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Baeche 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=baeche_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=baeche_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Baeche 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=baeche_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=baeche_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_03",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_03&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_04",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_04&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 5",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_05",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_05&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/7"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fluesse 6",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=fluss_06",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=fluss_06&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/7/8"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Seen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Seen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_3",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_3&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_4",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_4&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 5",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_5",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_5&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Seen 6",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=see_6",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=see_6&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/8/7"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wege",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Wege",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Wege&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wegenamen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=weg_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=weg_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wege 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=weg_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=weg_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wege 0 Fuss",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=weg_0_fuss",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=weg_0_fuss&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Wege 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=weg_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=weg_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fahrbahnachse",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Fahrbahn",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Fahrbahn&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Fährverbindungen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=faehre",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=faehre&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/9/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bauwerke",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bauwerke",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bauwerke&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Gebäude",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_gebaeude",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_gebaeude&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Turm",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_turm",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_turm&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Vorratsbehälter/Speicher",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_vorratsb",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_vorratsb&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sonstiges Bauwerk",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_sonstigesbw",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_sonstigesbw&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Sport/Freizeit/Erholung",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_bw_sfe",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_bw_sfe&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/10/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Gemeindestrassen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Gemeindestrassen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Gemeindestrassen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/11"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Gemeindestrassen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Gemeindestrasse_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Gemeindestrasse_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/11/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Gemeindestrassen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Gemeindestrasse_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Gemeindestrasse_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/11/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Kreisstrassen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Kreisstrassen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Kreisstrassen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/12"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Kreisstrassen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Kreisstrasse_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Kreisstrasse_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/12/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Kreisstrassen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Kreisstrasse_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Kreisstrasse_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/12/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Kreisstrassen 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Kreisstrasse_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Kreisstrasse_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/12/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesstrassen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesstrassen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesstrassen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/13"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesstrassen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesstrasse_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesstrasse_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/13/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesstrassen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesstrasse_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesstrasse_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/13/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesstrassen 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesstrasse_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesstrasse_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/13/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Landesstrassen 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Landesstrasse_3",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Landesstrasse_3&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/13/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bundesstrassen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bundesstrassen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bundesstrassen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/14"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bundesstrassen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bundesstrasse_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bundesstrasse_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/14/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bundesstrassen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bundesstrasse_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bundesstrasse_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/14/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bundesstrassen 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bundesstrasse_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bundesstrasse_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/14/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bundesstrassen 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bundesstrasse_3",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bundesstrasse_3&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/14/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Autobahnen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Autobahnen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Autobahnen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/15"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Autobahnen 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Autobahn_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Autobahn_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/15/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Autobahnen 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Autobahn_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Autobahn_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/15/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Autobahnen 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Autobahn_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Autobahn_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/15/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Autobahnen 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Autobahn_3",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Autobahn_3&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/15/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bahn",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Bahn",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Bahn&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/16"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bahn 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=bahn_00",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=bahn_00&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/16/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bahn 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=bahn_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=bahn_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/16/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bahn 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=bahn_02",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=bahn_02&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/16/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Bahnhof",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=bahnhof",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=bahnhof&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/16/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Ortschaften",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Ortschaften",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Ortschaften&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 01",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_01",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_01&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/1"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/2"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 2",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_2",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_2&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/3"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 3",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_3",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_3&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/4"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 4",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_4",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_4&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/5"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 5",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_5",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_5&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/6"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 6",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_6",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_6&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/7"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Orte 7",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=orte_7",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=orte_7&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/8"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Schutzhuetten 0",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=schutzhuette_0",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=schutzhuette_0&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/9"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Schutzhuetten 1",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=schutzhuette_1",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=schutzhuette_1&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/10"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Berggipfel",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=berge",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=berge&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/17/11"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Leitungen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=Leitungen",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=Leitungen&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/18"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Leitungen",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=ax_leitung",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=ax_leitung&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/18/0"
      }
  },
  {
      "type": "Feature",
      "properties": {
          "title": "Oberleitungsmast",
          "updated": "2024-05-03T10:26:38.477Z",
          "offerings": [
              {
                  "code": "http://www.opengis.net/spec/owc/1.0/req/wms",
                  "operations": [
                      {
                          "code": "GetCapabilitiess",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?",
                          "method": "GET",
                          "type": "application/xml"
                      },
                      {
                          "code": "GetMap",
                          "href": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?SERVICE=wms&VERSION=1.3.0&REQUEST=GetMap&FORMAT=image%2Fpng&LAYERS=leitungsmasten",
                          "method": "GET",
                          "type": "image/png"
                      }
                  ],
                  "styles": [
                      {
                          "name": "default",
                          "title": "default",
                          "legendURL": "https://geo5.service24.rlp.de/wms/karte_rp.fcgi?version=1.3.0&service=WMS&request=GetLegendGraphic&sld_version=1.1.0&layer=leitungsmasten&format=image/png&STYLE=default"
                      }
                  ]
              }
          ],
          "folder": "/0/18/1"
      }
  }
]

// till Flughafenflaeche layer (included)
export const reducedKarteRpFeatures: OWSResource[] = karteRpFeatures.slice(0, 28)