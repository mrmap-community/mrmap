import DnsIcon from "@mui/icons-material/Dns";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Card, Stack, Typography, type SvgIconProps } from "@mui/material";
import { useMemo, type ComponentType } from "react";
import { useListContext, useTranslate } from "react-admin";
import { Count } from "../../../../jsonapi/components/Count";
import { type ServiceListResource } from "./config";
import { withoutFacetKeys } from "./alertFacets";

/** what a tile above the list of services counts */
export interface SummaryTile {
  /** the key of the label of the tile */
  key: string;
  /** the resource which answers the count of the tile */
  resource: string;
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
 * Three of them count the resource of the list itself, so a screen of
 * catalogues counts catalogues and a screen of web feature services counts web
 * feature services. The running updates are not answered by the services: the
 * background process which updates a service does not name the kind of the
 * service it updates, so this tile keeps the global scope of the processes which
 * update anything and asks no filter of the services on it.
 */
export const summaryTiles = (resource: ServiceListResource): SummaryTile[] => [
  {
    key: "total",
    resource,
    icon: DnsIcon,
    color: "primary",
  },
  {
    key: "healthy",
    resource,
    filter: { has_alert: false },
    icon: VerifiedUserIcon,
    color: "success",
  },
  {
    key: "runningUpdates",
    resource: "BackgroundProcess",
    filter: { status: "pending,running", process_type: "update" },
    icon: PendingActionsIcon,
    color: "info",
  },
  {
    key: "needsAttention",
    resource,
    filter: { has_alert: true },
    icon: WarningAmberIcon,
    color: "warning",
  },
];

export interface ServiceSummaryTilesProps {
  /** the resource of the list the tiles are counted for */
  resource: ServiceListResource;
}

/**
 * How many services the current filters answer, per state of attention.
 *
 * Every tile is a count of the resource which answers it and nothing else: the
 * services are counted by the filters of the list, narrowed to the state of the
 * tile, and the running updates are counted by the background processes which do
 * not have an end yet. Because a count is asked from the api, a tile answers the
 * same number of services as the rows of the list do.
 */
const ServiceSummaryTiles = ({ resource }: ServiceSummaryTilesProps) => {
  const { filter } = useListContext();
  const translate = useTranslate();

  // the filters of the list are the scope of a tile, minus the ones the tiles
  // and the facets answer themselves
  const scope = useMemo(() => withoutFacetKeys(filter), [filter]);
  const tiles = useMemo(() => summaryTiles(resource), [resource]);

  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ flexWrap: "wrap", gap: 2, "& > *": { flex: "1 1 170px" } }}
    >
      {tiles.map((tile) => (
        <Card key={tile.key} sx={{ p: 2 }}>
          <Stack
            direction="row"
            spacing={1.5}
            sx={{ alignItems: "center", overflow: "hidden" }}
          >
            <tile.icon color={tile.color} fontSize="small" />
            <Stack sx={{ minWidth: 0 }}>
              <Typography
                variant="overline"
                color="text.secondary"
                noWrap
                title={translate(`serviceList.tiles.${tile.key}`)}
              >
                {translate(`serviceList.tiles.${tile.key}`)}
              </Typography>
              <Count
                resource={tile.resource}
                filter={{ ...scope, ...tile.filter }}
                link
                variant="h5"
                component="div"
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
