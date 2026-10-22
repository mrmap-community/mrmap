import { type FilterPayload } from "react-admin";

/**
 * The attributes which answer the attention of a service, as the filters of the
 * api name them.
 *
 * The facets of the list and the tiles above it narrow the services by these
 * attributes, so the keys which have to be replaced when another facet is chosen
 * are answered here and not in every component which filters by them.
 *
 * The names are the ones the filterset of a service declares
 * (registry/filters/service.py) and not the ones a response carries, because the
 * filter inputs which the filter button of a list offers take the name of the
 * filter of the api as their source (see jsonapi/hooks/useFilterInputForOpera-
 * tion.tsx). A facet and the filter of the same state which the filter button
 * offers are one and the same state this way, and never two contradictory
 * filters which the list would answer at once.
 */
export const ALERT_FILTER_KEYS: string[] = [
  "has_alert",
  "monitoring_failed",
  "monitoring_failed_at",
  "update_review_required",
  "update_review_required_at",
  "update_failed",
  "update_failed_at",
];

/**
 * The filter the list of services applies on its own. It is not a facet a user
 * chose, so it is not handed over to the filter of a facet.
 */
export const OWN_FILTER_KEYS: string[] = ["is_update_candidate"];

export interface StatusFacet {
  /** the key the facet is translated by and chosen with */
  key: string;
  /** the filter which narrows the services to the facet */
  filter?: Record<string, boolean>;
}

/**
 * The facets the list of services can be narrowed to. Every one of them is
 * answered by a filter on the attributes of the services themselves, which keeps
 * the facet, the tiles and the rows of the list three looks at one query.
 *
 * The facet of the services without an alert is named by what the api answers and
 * never by the health of a service: `has_alert` is false for a service which
 * passed its last monitoring run as it is for a service whose monitoring never
 * ran at all, so no answer of that filter says that a service was checked. The
 * state of the checks which are overdue is not answered by these attributes
 * either, because a crontab is no rule of the database (see
 * registry/querys/alerts.py).
 */
export const STATUS_FACETS: StatusFacet[] = [
  { key: "all" },
  { key: "needsAttention", filter: { has_alert: true } },
  { key: "noAlerts", filter: { has_alert: false } },
  { key: "monitoringFailed", filter: { monitoring_failed: true } },
  { key: "updateFailed", filter: { update_failed: true } },
  { key: "updateReviewRequired", filter: { update_review_required: true } },
];

/** whether a filter answers a boolean, which a filter from the url does */
const asBoolean = (value: unknown): boolean | undefined => {
  if (value === true || value === "true") {
    return true;
  }
  if (value === false || value === "false") {
    return false;
  }
  return undefined;
};

/**
 * The query a list answers: the filters a user chose and the filter the list
 * applies on its own.
 *
 * The list controller answers these two apart - the permanent filter of a list is
 * not one of the filters which are stored - so everything which asks what the list
 * answers has to merge them: the tiles above the rows, the facet which is lit and
 * the rows themselves. Reading only one of them answers another question than the
 * list does.
 */
export const queryOfList = (
  filter?: FilterPayload,
  filterValues?: FilterPayload,
): FilterPayload => ({ ...filterValues, ...filter });

/**
 * The filters of a query without the states of attention.
 *
 * The tiles above the list count one state each, so they narrow the query of the
 * list by the state of their own and by nothing else which answers attention.
 * Everything else the list asks - the search, the filters of the filter button
 * and the filter the list applies on its own - stays with the tile, because only
 * then does a tile answer the same services as the rows of the list do.
 */
export const withoutAlertKeys = (filter?: FilterPayload): FilterPayload =>
  Object.fromEntries(
    Object.entries(filter ?? {}).filter(
      ([key]) => !ALERT_FILTER_KEYS.includes(key),
    ),
  );

/**
 * The filters of the list without the ones a facet answers.
 *
 * A facet replaces the states of attention with the one which is chosen and never
 * carries the filter the list applies on its own, which the list adds itself.
 */
export const withoutFacetKeys = (filter?: FilterPayload): FilterPayload =>
  Object.fromEntries(
    Object.entries(withoutAlertKeys(filter)).filter(
      ([key]) => !OWN_FILTER_KEYS.includes(key),
    ),
  );

/** the facet the given filters answer, "all" if none of them does */
export const facetOf = (filter?: FilterPayload): string => {
  const hasAlert = asBoolean(filter?.has_alert);
  if (hasAlert === true) {
    return "needsAttention";
  }
  if (hasAlert === false) {
    return "noAlerts";
  }
  const facet = STATUS_FACETS.filter(
    (candidate) => candidate.filter !== undefined,
  ).find((candidate) =>
    Object.entries(candidate.filter ?? {}).every(
      ([key, value]) => asBoolean(filter?.[key]) === value,
    ),
  );
  return facet?.key ?? "all";
};

/**
 * The filters to narrow the list to one facet.
 *
 * The facet of all services is no narrowing at all: it answers the whole list,
 * so it resets every filter a user asked for, the search and the ones of the
 * filter button included. Every other facet keeps the filters which are not
 * ones of the facets, so choosing a facet does not throw away a search.
 *
 * Handed to the list as the whole filter, because a list replaces the filters it
 * stores with the ones it is given and keeps only the filter it applies on its
 * own. The filters of the services which are stored are given to this function -
 * and not the filters of the query, which carry that own filter too.
 */
export const filterForFacet = (
  filter: FilterPayload | undefined,
  key: string,
): FilterPayload => {
  if (key === "all") {
    return {};
  }
  const facet = STATUS_FACETS.find((candidate) => candidate.key === key);
  return { ...withoutFacetKeys(filter), ...facet?.filter };
};
