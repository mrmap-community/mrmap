import { useMemo, type ComponentType } from "react";
import { useListContext, useTranslate } from "react-admin";

import DnsIcon from "@mui/icons-material/Dns";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import SyncIcon from "@mui/icons-material/Sync";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  Card,
  Stack,
  Tooltip,
  Typography,
  type SvgIconProps,
} from "@mui/material";

import { Count } from "../../../../jsonapi/components/Count";
import {
  type StatusFacet,
  queryOfList,
  withoutAlertKeys,
} from "./alertFacets";

/** what a tile above the list of services counts */
export interface SummaryTile {
  /** the key of the label of the tile */
  key: string;
  /** the resource which answers the count of the tile */
  resource: string;
  /**
   * The scope of the count: the services of the query the list answers, or every
   * resource of the kind the tile counts. A tile of the registry asks nothing of
   * the list, because a filter of the services is no filter of its resource.
   */
  scope: "list" | "registry";
  /** the state of that resource the tile counts, all of it when unset */
  filter?: Record<string, unknown>;
  /** the icon which marks the tile, so a state is read before its label is */
  icon: ComponentType<SvgIconProps>;
  /** the color of that icon, which is the color of the state of the tile */
  color: "primary" | "success" | "info" | "warning";
}

/** the icon and the color of the tile which counts a facet of the harvesting */
const HARVEST_TILE_STATE: Record<
  string,
  { icon: ComponentType<SvgIconProps>; color: SummaryTile["color"] }
> = {
  harvestAborted: { icon: ReportProblemIcon, color: "warning" },
  harvestIncomplete: { icon: ErrorOutlineIcon, color: "warning" },
};

/**
 * The states the tiles above the list of services count.
 *
 * Some of them count the resource of the list itself and the query which is
 * asked of it, so a screen of catalogues counts catalogues and a screen of web
 * feature services counts web feature services - the search and the chosen
 * filters included. The processes which work right now are not answered by the
 * services: a background process does not name the kind of the service it works
 * on, so those tiles count the whole registry and ask no filter of the services
 * on it. Their labels say so, because a number of another scope is not
 * comparable to the rows below it.
 *
 * The tile of the services without an alert counts the state the api answers and
 * not a health: `has_alert` is false for a service whose monitoring never ran as
 * it is for a service which passed its last run, and a catalogue which was never
 * harvested is in that count too. A state which proves that a service was
 * checked recently is not answered by these attributes, and neither are the
 * schedules a service did not keep (#1082); what the harvesting of a catalogue
 * left behind is answered by the facets of the harvesting, which a screen which
 * declares them gets tiles of by the same answer.
 */
export const summaryTiles = (
  resource: string,
  harvestFacets: StatusFacet[] = [],
): SummaryTile[] => [
  {
    key: "total",
    resource,
    scope: "list",
    icon: DnsIcon,
    color: "primary",
  },
  {
    key: "noAlerts",
    resource,
    scope: "list",
    filter: { has_alert: false },
    icon: VerifiedUserIcon,
    color: "success",
  },
  {
    key: "runningUpdates",
    resource: "BackgroundProcess",
    scope: "registry",
    filter: { status: "pending,running", process_type: "update" },
    icon: PendingActionsIcon,
    color: "info",
  },
  // the harvestings which work right now are asked of the same resource and by
  // the same shape as the updates, because a harvesting process names no catalogue
  ...(harvestFacets.length > 0
    ? [
        {
          key: "runningHarvests",
          resource: "BackgroundProcess",
          scope: "registry",
          filter: { status: "pending,running", process_type: "harvesting" },
          icon: SyncIcon,
          color: "info",
        } satisfies SummaryTile,
      ]
    : []),
  // one tile per facet of the harvesting: the same key and the same filter, so a
  // tile counts exactly what the facet narrows the rows to
  ...harvestFacets.map((facet): SummaryTile => ({
    key: facet.key,
    resource,
    scope: "list",
    filter: facet.filter,
    icon: HARVEST_TILE_STATE[facet.key].icon,
    color: HARVEST_TILE_STATE[facet.key].color,
  })),
  {
    key: "needsAttention",
    resource,
    scope: "list",
    filter: { has_alert: true },
    icon: WarningAmberIcon,
    color: "warning",
  },
];

/**
 * The filters a tile is counted by, which are the filters its link opens.
 *
 * A tile of the list narrows the query of the list to the state of the tile, a
 * tile of the registry asks its own filter and nothing else - so the count of a
 * tile and the list which its link opens always answer the same records.
 */
export const filterOfTile = (
  tile: SummaryTile,
  scope: Record<string, unknown>,
): Record<string, unknown> =>
  tile.scope === "list" ? { ...scope, ...tile.filter } : { ...tile.filter };

/**
 * How many services the current filters answer, per state of attention.
 *
 * Every tile is a count of the resource which answers it and nothing else: the
 * services are counted by the query of the list - the filters a user chose and the
 * filter the list applies on its own - narrowed to the state of the tile, and the
 * processes which work right now are counted by the background processes which
 * do anything and do not have an end yet. Because a count is asked from the api, a
 * tile answers the same number of services as the rows of the list do, and a count
 * the api refuses is marked instead of answered as none.
 *
 * The screen gives the facets of the harvesting it declares: the tiles of those
 * states are there where the facets are, and nowhere else.
 */
const ServiceSummaryTiles = ({
  harvestFacets = [],
}: {
  /** the facets of the harvesting which the resource of the screen declares */
  harvestFacets?: StatusFacet[];
}) => {
  const { filter, filterValues, resource } = useListContext();
  const translate = useTranslate();

  // the query of the list, minus the states of attention which the tiles answer
  // themselves: a tile counts the services the list answers in the state of the
  // tile and nothing else
  const scope = useMemo(
    () => withoutAlertKeys(queryOfList(filter, filterValues)),
    [filter, filterValues],
  );
  const tiles = useMemo(
    () =>
      resource !== undefined
        ? summaryTiles(resource, harvestFacets)
        : [],
    [resource, harvestFacets],
  );

  return (
    <Stack
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(4, minmax(0, 1fr))" },
        width: "100%",
        gap: 2,
      }}
    >
      {tiles.map((tile) => (
        <Card key={tile.key} variant="outlined" sx={{ p: 2, minWidth: 0 }}>
          <Stack
            direction="row"
            spacing={1.5}
            sx={{ alignItems: "center", height: "100%" }}
          >
            <tile.icon color={tile.color} />
            <Stack sx={{ minWidth: 0 }}>
              <Tooltip title={translate(`serviceList.tiles.hints.${tile.key}`)}>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {translate(`serviceList.tiles.${tile.key}`)}
                </Typography>
              </Tooltip>
              <Count
                resource={tile.resource}
                filter={filterOfTile(tile, scope)}
                link
                variant="h5"
                refetchInterval={60000}
              />
            </Stack>
          </Stack>
        </Card>
      ))}
    </Stack>
  );
};

export default ServiceSummaryTiles;
