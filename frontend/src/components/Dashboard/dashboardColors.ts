import type { Theme } from "@mui/material/styles";

/**
 * The color a resource is drawn with on the dashboard.
 *
 * The activity chart (#1818) fixes these colors and the inventory, stacked and
 * distribution charts (#1820) draw the same resources again, so one resource
 * must never mean two colors on one screen. The keys are JSON:API types and the
 * values are palette colors of the existing theme — the same
 * `theme.palette[color].main` reading the chips of `ServiceDetailsCard` use.
 */
const RESOURCE_COLORS = {
  CatalogueService: "warning",
  DatasetMetadataRecord: "success",
  ServiceMetadataRecord: "primary",
} as const;

/**
 * The color of one resource.
 *
 * A resource without an entry is drawn neutral on purpose: two of them would
 * otherwise share a palette color unnoticed. #1820 adds the entries of the
 * resources its own charts draw.
 */
export const dashboardResourceColor = (theme: Theme, resource: string): string => {
  const color = RESOURCE_COLORS[resource as keyof typeof RESOURCE_COLORS];
  return color ? theme.palette[color].main : theme.palette.grey[500];
};
