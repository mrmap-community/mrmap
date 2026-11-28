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
 * The four inventory kinds the donut of #1820 counts and neither the inventory
 * line (#1817) nor the stacked bars (#1820) draw: the theme has no palette slot
 * left for them beside the three of #1818, so each keeps one distinct Material
 * hue, far enough from the three palette colors to tell the arcs apart.
 */
const INVENTORY_COLORS: Record<string, string> = {
  WebMapService: "#6a1b9a",
  Layer: "#455a64",
  WebFeatureService: "#00838f",
  FeatureType: "#c2185b",
};

/**
 * The color of one resource.
 *
 * A resource without an entry is drawn neutral on purpose: two of them would
 * otherwise share a palette color unnoticed.
 */
export const dashboardResourceColor = (theme: Theme, resource: string): string => {
  const color = RESOURCE_COLORS[resource as keyof typeof RESOURCE_COLORS];
  if (color) return theme.palette[color].main;
  return INVENTORY_COLORS[resource] ?? theme.palette.grey[500];
};
