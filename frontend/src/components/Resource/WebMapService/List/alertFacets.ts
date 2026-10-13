import { type FilterPayload } from "react-admin";

/**
 * The attributes which answer the attention of a service, as the api names them.
 *
 * The facets of the list and the tiles above it narrow the services by these
 * attributes, so the keys which have to be replaced when another facet is chosen
 * are answered here and not in every component which filters by them.
 */
export const ALERT_FILTER_KEYS: string[] = [
  "hasAlert",
  "monitoringFailed",
  "monitoringFailedAt",
  "updateReviewRequired",
  "updateReviewRequiredAt",
  "updateFailed",
  "updateFailedAt",
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
 */
export const STATUS_FACETS: StatusFacet[] = [
  { key: "all" },
  { key: "needsAttention", filter: { hasAlert: true } },
  { key: "healthy", filter: { hasAlert: false } },
  { key: "monitoringFailed", filter: { monitoringFailed: true } },
  { key: "updateFailed", filter: { updateFailed: true } },
  { key: "updateReviewRequired", filter: { updateReviewRequired: true } },
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

/** the filters of the list without the ones a facet or a tile answers */
export const withoutFacetKeys = (filter?: FilterPayload): FilterPayload =>
  Object.fromEntries(
    Object.entries(filter ?? {}).filter(
      ([key]) =>
        !ALERT_FILTER_KEYS.includes(key) && !OWN_FILTER_KEYS.includes(key),
    ),
  );

/** the facet the given filters answer, "all" if none of them does */
export const facetOf = (filter?: FilterPayload): string => {
  const hasAlert = asBoolean(filter?.hasAlert);
  if (hasAlert === true) {
    return "needsAttention";
  }
  if (hasAlert === false) {
    return "healthy";
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
 * The filters to narrow the list to one facet, which keeps every filter the user
 * asked for besides the ones the facets are answered by.
 */
export const filterForFacet = (
  filter: FilterPayload | undefined,
  key: string,
): FilterPayload => {
  const facet = STATUS_FACETS.find((candidate) => candidate.key === key);
  return { ...withoutFacetKeys(filter), ...facet?.filter };
};
