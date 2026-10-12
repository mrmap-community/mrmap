export const wmsUpdateConfig = {
  serviceResource: "WebMapService",
  mappingResource: "LayerMapping",
  elementResource: "Layer",
  elements: "layers",
  oldElement: "oldLayer",
  newElement: "newLayer",
  selectedParam: "selectedLayer",
  historyResource: "HistoricalLayer",
  hasTree: true,
} as const;

export const wfsUpdateConfig = {
  serviceResource: "WebFeatureService",
  mappingResource: "FeatureTypeMapping",
  elementResource: "FeatureType",
  elements: "featuretypes",
  oldElement: "oldFeaturetype",
  newElement: "newFeaturetype",
  selectedParam: "selectedFeatureType",
  historyResource: "HistoricalFeatureType",
  hasTree: false,
} as const;

export type ServiceUpdateConfig =
  typeof wmsUpdateConfig | typeof wfsUpdateConfig;
