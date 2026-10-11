import type { FeatureCollection, Geometry } from "geojson";
import type { RaRecord } from "react-admin";

// The proxy matches stored layer memberships. Rule validation requires complete subtrees.
// An undefined group uses rules already filtered by the API for a selected user.
export const getSpatialAccess = (
  rules: RaRecord[],
  group: string | undefined,
  operation: string,
  layer: string,
  hasServiceRules = rules.length > 0,
) => {
  const matching = rules.filter(
    (rule) =>
      (group === undefined ||
        rule.allowedGroups.length === 0 ||
        rule.allowedGroups.some(
          (item: RaRecord) => String(item.id) === group,
        )) &&
      rule.operations.some((item: RaRecord) => String(item.id) === operation) &&
      rule.securedLayers.some((item: RaRecord) => String(item.id) === layer),
  );
  const status =
    !hasServiceRules || matching.some((rule) => rule.allowedArea == null)
      ? "unrestricted"
      : matching.length
        ? "restricted"
        : "denied";
  const areas: FeatureCollection<Geometry> = {
    type: "FeatureCollection",
    features:
      status === "restricted"
        ? matching.map((rule) => ({
            type: "Feature",
            properties: {},
            geometry: rule.allowedArea as Geometry,
          }))
        : [],
  };
  return { status, areas };
};
