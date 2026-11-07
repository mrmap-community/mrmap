import { type ComponentType } from "react";
import { type SortPayload, useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import RateReviewIcon from "@mui/icons-material/RateReview";
import SyncIcon from "@mui/icons-material/Sync";
import SyncProblemIcon from "@mui/icons-material/SyncProblem";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Stack, Typography, type SvgIconProps } from "@mui/material";

import { Count } from "../../../jsonapi/components/Count";
import SimpleCard from "../../MUI/SimpleCard";
import { ACTIVE_STATUSES } from "../../Resource/BackgroundProcess/ListBackgroundProcess";

/**
 * One queue of the work an administrator has to look at.
 *
 * A queue is counted by the api and links to the list which answers the very
 * records of that count, so the number of a queue and the list its link opens
 * always answer the same records.
 */
export interface WorkQueue {
  /** the key the queue is translated by */
  key: string;
  /** the resource which answers the count of the queue */
  resource: string;
  /** the state of that resource the queue counts, all of it when unset */
  filter?: Record<string, unknown>;
  /** an ordering supported by the resource's collection endpoint */
  sort?: SortPayload;
  /** the icon which marks the queue, so a queue is read before its label is */
  icon: ComponentType<SvgIconProps>;
  /** the color of that icon, which is the color of the state of the queue */
  color: "error" | "warning" | "info";
}

/** the categories which the harvesting of a catalogue leaves behind, as the
 *  alerts api names them; its category filter answers several of them comma
 *  separated with one request (registry/views/alerts.py, #1086) */
const HARVEST_ALERT_CATEGORIES = [
  "harvest_aborted",
  "harvest_incomplete",
  "harvest_overdue",
  "harvest_schedule_too_tight",
];

/**
 * The queues of the whole deployment which the dashboard answers above the
 * inventory.
 *
 * The alerts are counted by the collection of the service alerts, which
 * answers the category of an alert and the kind of service the alert belongs
 * to - `filter[category]` and `filter[serviceType]` (registry/views/alerts.py)
 * - so every queue of the alerts names the states and, where it is narrowed,
 * the kind of service it counts. The work is counted by the background
 * processes, which do not name the kind of the resource they work on; a queue
 * of them names its process type, a queue without one counts all work.
 * Nothing of the card is counted per screen: its subheader says that every
 * queue counts over everything the caller may read.
 */
export const workQueues = (): WorkQueue[] => [
  {
    key: "alerts",
    resource: "ServiceAlert",
    sort: { field: "severity,-occurredAt", order: "ASC" },
    icon: WarningAmberIcon,
    color: "warning",
  },
  {
    key: "updateReviews",
    resource: "ServiceAlert",
    filter: { category: "update_review_required" },
    sort: { field: "severity,-occurredAt", order: "ASC" },
    icon: RateReviewIcon,
    color: "warning",
  },
  // the harvesting states are only answered by a catalogue, so the queue
  // names the kind of service it counts - monitoring alerts of a map service
  // must never push the broken catalogues out of this queue
  {
    key: "harvestAlerts",
    resource: "ServiceAlert",
    filter: {
      category: HARVEST_ALERT_CATEGORIES.join(","),
      serviceType: "CatalogueService",
    },
    sort: { field: "severity,-occurredAt", order: "ASC" },
    icon: SyncProblemIcon,
    color: "warning",
  },
  {
    key: "runningWork",
    resource: "BackgroundProcess",
    filter: { status: ACTIVE_STATUSES },
    icon: PendingActionsIcon,
    color: "info",
  },
  // a harvesting process names no catalogue, so the queue counts the runs of
  // every catalogue - the same shape as the running updates tile of the list
  {
    key: "runningHarvests",
    resource: "BackgroundProcess",
    filter: { status: ACTIVE_STATUSES, process_type: "harvesting" },
    icon: SyncIcon,
    color: "info",
  },
  {
    key: "failedWork",
    resource: "BackgroundProcess",
    filter: { status: "failed" },
    icon: ErrorIcon,
    color: "error",
  },
];

/**
 * The queues the api counts, above the inventory of the deployment.
 *
 * Every queue is a count of the api and not a sum of the records a screen shows:
 * the api answers the records the user is permitted to see and their total, so a
 * queue never counts more than the user may read and never less because a page
 * of it is not loaded. A count the api refuses is marked by an error icon and is
 * therefore never read as no work - only a zero says that nothing waits.
 */
const WorkQueueCard = () => {
  const translate = useTranslate();

  return (
    <SimpleCard
      title={translate("dashboard.workQueue.title")}
      subheader={translate("dashboard.workQueue.scope")}
      cardProps={{ sx: { boxShadow: 4, height: "auto", width: "100%" } }}
      contentProps={{ sx: { pt: 1.5, pb: 2 } }}
    >
      <Stack
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            sm: "repeat(2, minmax(0, 1fr))",
            lg: "repeat(3, minmax(0, 1fr))",
          },
          width: "100%",
          gap: 2,
        }}
      >
        {workQueues().map((queue) => (
          <Stack
            key={queue.key}
            direction="row"
            spacing={1.5}
            sx={{ alignItems: "center", minWidth: 0 }}
          >
            <queue.icon color={queue.color} />
            <Stack sx={{ minWidth: 0 }}>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ overflowWrap: "anywhere" }}
              >
                {translate(`dashboard.workQueue.${queue.key}`)}
              </Typography>
              <Count
                resource={queue.resource}
                filter={queue.filter}
                sort={queue.sort}
                link
                variant="h5"
                refetchInterval={60000}
              />
            </Stack>
          </Stack>
        ))}
      </Stack>
    </SimpleCard>
  );
};

export default WorkQueueCard;
