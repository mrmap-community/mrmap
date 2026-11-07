import type { ServiceProtocol } from "../ServiceShow/ServiceDetailsCard";

import type { ComponentType } from "react";
import type { DatagridProps } from "react-admin";

/** the kinds of services the screen of registered services answers */
export type ServiceListResource =
  "WebMapService" | "WebFeatureService" | "CatalogueService";

/**
 * The filters of the harvesting which the filterset of a resource declares
 * (registry/filters/service.py).
 *
 * They are named by the filter of the api and not by an attribute of a response,
 * which is what keeps a facet, the tile which counts it and the filter which the
 * filter button offers one and the same state.
 */
export type HarvestFilter = "harvest_aborted" | "harvest_incomplete";

/**
 * What differs between the lists of the registered services.
 *
 * The lists themselves are one screen: only the resource the api is asked for,
 * the protocol the details panel shows a service with, the label and the source
 * of the count of the elements of a service, the attributes a request names in
 * its sparse fieldset, the states of the harvesting which its resource declares
 * and the action which the rows of one kind of service answer apart are
 * configured per resource.
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
  /**
   * What the resource of the screen answers of the harvesting of its services,
   * as its filterset declares it.
   *
   * A catalogue is harvested and no other kind of service is, so the rows, the
   * facets and the tiles which speak of the harvesting follow this one answer of
   * the config: a resource which names no filter of the harvesting is asked none
   * of them and shows none of them.
   */
  harvestFilters?: HarvestFilter[];
  /** the action which the rows of the resource answer apart from the standard
   *  actions; it is rendered inside the record context of the row */
  RowAction?: ComponentType;
  /** Optional actions for the datagrid's selected services. */
  BulkActions?: ComponentType;
  isRowSelectable?: DatagridProps["isRowSelectable"];
}
