import type { ServiceProtocol } from "../ServiceShow/ServiceDetailsCard";

import type { ComponentType } from "react";

/** the kinds of services the screen of registered services answers */
export type ServiceListResource =
  "WebMapService" | "WebFeatureService" | "CatalogueService";

/**
 * What differs between the lists of the registered services.
 *
 * The lists themselves are one screen: only the resource the api is asked for,
 * the protocol the details panel shows a service with, the label and the source
 * of the count of the elements of a service, the attributes a request names in
 * its sparse fieldset and the action which the rows of one kind of service
 * answer apart are configured per resource.
 */
export interface ServiceListConfig {
  /** the resource the list answers */
  resource: ServiceListResource;
  /** the protocol the details panel of a selected service shows the service with */
  protocol: ServiceProtocol;
  /** the key of the label of the column which counts the elements of a service,
   *  below "serviceList.columns" */
  countLabelKey: "layers" | "featureTypes" | "records";
  /** the property of a record which answers the elements of a service as a
   *  relationship, which counts them when the page does not carry the count of
   *  them - unset for a resource which does not answer the elements of a service
   *  within its records */
  countRelation?: string;
  /** the attributes the list asks for, as the api names them in a sparse fieldset */
  fields: string[];
  /** the action which the rows of the resource answer apart from the standard
   *  actions; it is rendered inside the record context of the row */
  RowAction?: ComponentType;
  /** Optional actions for the datagrid's selected services. */
  BulkActions?: ComponentType;
}
