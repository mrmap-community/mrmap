import { type ComponentType, useCallback, useMemo, useState } from "react";
import {
  Link,
  useCreatePath,
  type SortPayload,
  useTranslate,
} from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import LockIcon from "@mui/icons-material/Lock";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import RateReviewIcon from "@mui/icons-material/RateReview";
import SyncIcon from "@mui/icons-material/Sync";
import SyncProblemIcon from "@mui/icons-material/SyncProblem";
import {
  Box,
  Chip,
  List,
  ListItem,
  ListItemText,
  Typography,
  type SvgIconProps,
} from "@mui/material";

import { useSystemStatus } from "../../../context/SystemStatusContext";
import { Count, type CountState } from "../../../jsonapi/components/Count";
import SimpleCard from "../../MUI/SimpleCard";
import { ACTIVE_STATUSES } from "../../Resource/BackgroundProcess/ListBackgroundProcess";

/** what a queue counts, which decides the word and the color of its answer:
 *  `running` counts work the deployment is doing right now, `attention` counts
 *  records an administrator owes */
export type QueueKind = "running" | "attention";

/**
 * One queue of the deployment the health card answers.
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
  /** whether the queue counts work in progress or attention an administrator owes */
  kind: QueueKind;
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

/** the alerts of the catalogues, counted with one request of the alerts api */
const HARVEST_ALERT_FILTER = {
  category: HARVEST_ALERT_CATEGORIES.join(","),
  serviceType: "CatalogueService",
};

/** the alerts which ask for the review of an update, with one request */
const UPDATE_REVIEW_FILTER = { category: "update_review_required" };

/** the alerts ordered as the api orders them, so a row always answers the most
 *  severe alert of its category first */
const ALERT_SORT: SortPayload = { field: "severity,-occurredAt", order: "ASC" };

/**
 * The queues of the whole deployment the health card answers.
 *
 * The alerts are counted by the collection of the service alerts, which answers
 * the category of an alert and the kind of service the alert belongs to -
 * `filter[category]` and `filter[serviceType]` (registry/views/alerts.py) - so
 * every queue of the alerts names the states it counts and, where it is
 * narrowed, the kind of service. The work is counted by the background
 * processes, which do not name the kind of the resource they work on; a queue
 * of them names its process type.
 *
 * The alerts of every category are deliberately not a queue of their own: the
 * attention card beside this one already asks them with `useServiceAlerts`, so
 * a queue of all alerts would ask the api for the very same records twice
 * (#1816).
 *
 * The queues overlap - every update review and every harvesting alert is an
 * alert of a service - so they are answered as rows of their own and never
 * added up: a sum of them would count one alert twice.
 */
export const workQueues = (): WorkQueue[] => [
  {
    key: "runningWork",
    resource: "BackgroundProcess",
    filter: { status: ACTIVE_STATUSES },
    icon: PendingActionsIcon,
    kind: "running",
  },
  // a harvesting process names no catalogue, so the queue counts the runs of
  // every catalogue - the same shape as the running updates tile of the list
  {
    key: "runningHarvests",
    resource: "BackgroundProcess",
    filter: { status: ACTIVE_STATUSES, process_type: "harvesting" },
    icon: SyncIcon,
    kind: "running",
  },
  {
    key: "updateReviews",
    resource: "ServiceAlert",
    filter: UPDATE_REVIEW_FILTER,
    sort: ALERT_SORT,
    icon: RateReviewIcon,
    kind: "attention",
  },
  // the harvesting states are only answered by a catalogue, so the queue names
  // the kind of service it counts - monitoring alerts of a map service must
  // never push the broken catalogues out of this queue
  {
    key: "harvestAlerts",
    resource: "ServiceAlert",
    filter: HARVEST_ALERT_FILTER,
    sort: ALERT_SORT,
    icon: SyncProblemIcon,
    kind: "attention",
  },
  {
    key: "failedWork",
    resource: "BackgroundProcess",
    filter: { status: "failed" },
    icon: ErrorIcon,
    kind: "attention",
  },
];

/** what one row learned from the read of its own count */
interface RowAnswer {
  state: CountState;
  total?: number;
}

/** the answer of the card as a whole, which its subheader says: the states of
 *  the queues are not one state, and a card which read four of five queues must
 *  not read as the answer of five */
const cardScope = (
  answers: Record<string, RowAnswer>,
  queues: WorkQueue[],
  health: string,
) => {
  const states = queues.map((queue) => answers[queue.key]?.state);
  if (states.every((state) => state === undefined || state === "loading"))
    return "loading";
  // the machinery decides over the deployment: nothing which runs on workers
  // which do not run can read as healthy
  if (health === "down") return "down";
  const unread = states.filter(
    (state) => state === "error" || state === "forbidden",
  );
  const read = states.filter((state) => state === "zero" || state === "value");
  if (unread.length === queues.length) return "unreadable";
  if (unread.length > 0 && read.length > 0) return "partial";
  const waiting = queues.some(
    (queue) =>
      (answers[queue.key]?.total ?? 0) > 0 && queue.kind === "attention",
  );
  if (waiting) return "watch";
  if (states.includes("value")) return "running";
  // only a status which says so answers healthy, and never while a queue of
  // them was not read - that is the false green this card exists to prevent
  if (health === "healthy" && read.length === queues.length) return "healthy";
  return "idle";
};

/** the severity a queue answers with once it does hold records: work which runs
 *  answers the color of the deployment, an error of the work answers an error
 *  and everything an administrator owes answers a warning. The chip of a row and
 *  the icon of the very row answer the same severity, so a row cannot answer two
 *  different things about what waits in it */
const severityOf = (queue: WorkQueue): "primary" | "error" | "warning" => {
  if (queue.kind === "running") return "primary";
  return queue.key === "failedWork" ? "error" : "warning";
};

/** the chip of a row: a number answers what waits, a word answers a state a
 *  number cannot. A queue which is loading, which may not be read or which
 *  holds nothing ever answers the neutral outline instead of a success color: a
 *  queue which looks cleared is the false green this card exists to prevent */
const rowChip = (
  queue: WorkQueue,
  answer: RowAnswer,
  translate: (key: string) => string,
) => {
  const { state, total } = answer;
  if (state === "loading")
    return (
      <Chip
        size="small"
        variant="outlined"
        color="default"
        label={translate("systemStatus.checking")}
      />
    );
  if (state === "forbidden")
    return (
      <Chip
        size="small"
        variant="outlined"
        color="default"
        icon={<LockIcon />}
        label={translate("dashboard.workQueue.notPermitted")}
      />
    );
  if (state === "error")
    return (
      <Chip
        size="small"
        variant="outlined"
        color="error"
        label={translate("dashboard.workQueue.unreadable")}
      />
    );
  const running = queue.kind === "running";
  if (!total) {
    const emptiness = translate(
      running ? "dashboard.workQueue.idle" : "dashboard.workQueue.none",
    );
    return (
      <Chip
        size="small"
        variant="outlined"
        color="default"
        icon={<HourglassEmptyIcon />}
        label={emptiness}
      />
    );
  }
  const waiting = translate(
    running ? "dashboard.workQueue.running" : "dashboard.workQueue.waiting",
  );
  return (
    <Chip
      size="small"
      variant="outlined"
      color={severityOf(queue)}
      label={waiting}
    />
  );
};

/**
 * The compact health of the deployment: what runs, what waits and what nobody
 * can read.
 *
 * One row per queue, so an administrator reads the state of a queue before its
 * number and opens the very records behind it from the row. The rows count over
 * everything the caller may read and are never added up, and every answer of a
 * read is distinguished from the others: a queue which is loading is not a
 * queue which is idle, a queue the caller may not read is not an empty one and
 * a queue the api refused is neither. None of them answers green, because a
 * deployment whose workers do not run has to read as such.
 *
 * The state of the machinery is read from the context of the system status,
 * which the app bar already polls (#833), so the card asks nothing of its own
 * and cannot disagree with the indicator beside the title. A queue with nothing
 * to say still answers its row - a missing row is read as a queue which was not
 * asked at all - but the card stays as compact as its rows are and never grows
 * into a banner of its own.
 */
const WorkQueueCard = () => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const { health } = useSystemStatus();
  const queues = useMemo(workQueues, []);
  const [answers, setAnswers] = useState<Record<string, RowAnswer>>({});
  const report = useCallback(
    (key: string) => (state: CountState, total?: number) =>
      setAnswers((previous) =>
        previous[key]?.state === state && previous[key]?.total === total
          ? previous
          : { ...previous, [key]: { state, total } },
      ),
    [],
  );

  return (
    <SimpleCard
      title={translate("systemStatus.title")}
      subheader={translate(
        `dashboard.workQueue.scope.${cardScope(answers, queues, health)}`,
      )}
      cardProps={{ sx: { boxShadow: 4, height: "auto", width: "100%" } }}
      contentProps={{ sx: { pt: 0.5, pb: 0.5 } }}
    >
      <List disablePadding>
        {queues.map((queue) => {
          const answer = answers[queue.key];
          // the icon answers the severity of the queue only once its records
          // were read - a queue which is loading, may not be read or holds
          // nothing is answered neutral, never colored
          const iconColor =
            answer?.state === "value" ? severityOf(queue) : "disabled";
          return (
            <ListItem
              key={queue.key}
              disableGutters
              divider
              sx={{ py: 0.75, alignItems: "center" }}
            >
              <queue.icon fontSize="small" color={iconColor} />
              <ListItemText
                sx={{ ml: 1, minWidth: 0 }}
                primary={
                  <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                    <Link
                      to={{
                        pathname: createPath({
                          resource: queue.resource,
                          type: "list",
                        }),
                        search: queue.filter
                          ? `filter=${JSON.stringify(queue.filter)}`
                          : undefined,
                      }}
                    >
                      {translate(`dashboard.workQueue.${queue.key}`)}
                    </Link>
                  </Typography>
                }
                secondary={
                  <Count
                    resource={queue.resource}
                    filter={queue.filter}
                    sort={queue.sort}
                    link
                    variant="inherit"
                    refetchInterval={60000}
                    onStateChange={report(queue.key)}
                  />
                }
              />
              <Box sx={{ pl: 1, flexShrink: 0 }}>
                {rowChip(queue, answer ?? { state: "loading" }, translate)}
              </Box>
            </ListItem>
          );
        })}
      </List>
    </SimpleCard>
  );
};

export default WorkQueueCard;
