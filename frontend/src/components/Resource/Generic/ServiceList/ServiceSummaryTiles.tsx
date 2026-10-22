import { useMemo, type ComponentType } from "react";
import { useListContext, useTranslate } from "react-admin";

import DnsIcon from "@mui/icons-material/Dns";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
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
import { queryOfList, withoutAlertKeys } from "./alertFacets";

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

/**
 * The states the tiles above the list of services count.
 *
 * Three of them count the resource of the list itself and the query which is
 * asked of it, so a screen of catalogues counts catalogues and a screen of web
 * feature services counts web feature services - the search and the chosen
 * filters included. The running updates are not answered by the services: a
 * background process does not name the kind of the service it updates, so this
 * tile counts the whole registry and asks no filter of the services on it. Its
 * label says so, because a number of another scope is not comparable to the rows
 * below it.
 *
 * The tile of the services without an alert counts the state the api answers and
 * not a health: `has_alert` is false for a service whose monitoring never ran as
 * it is for a service which passed its last run. A state which proves that a
 * service was checked recently, and the schedules a service did not keep, are not
 * answered by these attributes and are the subject of the follow-up issue.
 */
export const summaryTiles = (resource: string): SummaryTile[] => [
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
 * running updates are counted by the background processes which update anything
 * and do not have an end yet. Because a count is asked from the api, a tile
 * answers the same number of services as the rows of the list do, and a count the
 * api refuses is marked instead of answered as none.
 */
const ServiceSummaryTiles = () => {
  const { filter, filterValues, resource } = useListContext();
  const translate = useTranslate();

  // the query of the list, minus the states of attention which the tiles answer
  // themselves: a tile counts the services the list answers in the state of the
  // tile and nothing else
  const scope = useMemo(
    () => withoutAlertKeys(queryOfList(filter, filterValues)),
    [filter, filterValues],
  );
  const tiles = useMemo(() => resource !== undefined ? summaryTiles(resource): [], [resource]);

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
