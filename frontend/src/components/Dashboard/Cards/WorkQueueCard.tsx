import { type ComponentType } from "react";
import { useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import RateReviewIcon from "@mui/icons-material/RateReview";
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
  /** the icon which marks the queue, so a queue is read before its label is */
  icon: ComponentType<SvgIconProps>;
  /** the color of that icon, which is the color of the state of the queue */
  color: "error" | "warning" | "info";
}

/**
 * The queues of the whole deployment which the dashboard answers above the
 * inventory.
 *
 * The alerts and the reviews are counted by the collection of the service
 * alerts, because that collection is what the api answers as the attention of
 * the services - it names the categories of the alerts and does not ask which
 * kind of service an alert belongs to. The work is counted by the background
 * processes, which do not name the kind of the resource they work on and are
 * therefore never counted by a resource of the registry.
 */
export const workQueues = (): WorkQueue[] => [
  {
    key: "alerts",
    resource: "ServiceAlert",
    icon: WarningAmberIcon,
    color: "warning",
  },
  {
    key: "updateReviews",
    resource: "ServiceAlert",
    filter: { category: "update_review_required" },
    icon: RateReviewIcon,
    color: "warning",
  },
  {
    key: "runningWork",
    resource: "BackgroundProcess",
    filter: { status: ACTIVE_STATUSES },
    icon: PendingActionsIcon,
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
            lg: "repeat(4, minmax(0, 1fr))",
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
