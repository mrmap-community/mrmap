import { type ReactNode, useMemo, useState } from "react";
import {
  Link,
  RecordContext,
  useCreatePath,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";

import AutorenewIcon from "@mui/icons-material/Autorenew";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ScheduleIcon from "@mui/icons-material/Schedule";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import TabContext from "@mui/lab/TabContext";
import TabList from "@mui/lab/TabList";
import TabPanel from "@mui/lab/TabPanel";
import {
  Alert,
  Box,
  Button,
  Card,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  InputAdornment,
  Stack,
  Tab,
  TextField,
  Typography,
} from "@mui/material";

import { Count } from "../../../../jsonapi/components/Count";
import RealtimeListBase from "../../../../jsonapi/components/Realtime/RealtimeListBase";
import ProgressField from "../../../Field/ProgressField";
import RelativeDateField from "../../../Field/RelativeDateField";
import AbortBackgroundProcessButton from "../AbortBackgroundProcessButton";
import ProcessStatusField from "../ProcessStatusField";
import { useBackgroundJobCenter } from "./BackgroundJobCenterContext";
import {
  completedWithinDayFilter,
  COUNTS_POLL_MILLISECONDS,
  JOB_COUNT_FILTERS,
  JOB_COUNT_SORT,
} from "./counts";
import {
  groupJobs,
  hasProgressTotal,
  jobStateOf,
  type BackgroundJobRecord,
  type JobTab,
  visibleJobs,
  type JobState,
  MAX_TRACKED_JOBS,
} from "./jobStore";

/** the rows one tab renders from the bounded store before it points at the
 *  full history screen - the drawer never renders thousands of rows (#1206) */
const MAX_RENDERED_ROWS = 50;

/** a tab panel fills the remaining height of the drawer and scrolls itself;
 *  MUI hides an inactive panel with the `hidden` attribute, which the flex
 *  display below would override - so the hidden case is answered explicitly */
const TAB_PANEL_SX = {
  p: 0,
  flex: 1,
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  "&[hidden]": { display: "none" },
} as const;

const STATE_ICONS: Record<JobState, ReactNode> = {
  queued: <ScheduleIcon color="action" />,
  running: <SyncIcon color="info" />,
  retrying: <AutorenewIcon color="warning" />,
  failed: <ErrorOutlinedIcon color="error" />,
  completed: <CheckCircleOutlinedIcon color="success" />,
  aborted: <CancelIcon color="disabled" />,
};

interface GroupedJobListProps {
  records: BackgroundJobRecord[];
  total: number;
}

/**
 * A row of one process.
 *
 * It reads the process from the record context and reuses the field
 * components of the resource: `ProcessStatusField` for the state chip,
 * `ProgressField` for the bar (indeterminate while the total is unknown),
 * `RelativeDateField` for the moment and `AbortBackgroundProcessButton` for
 * the only action the backend supports on a running process. There is no
 * retry: no api endpoint restarts a decided process, so the drawer offers no
 * such button (#1208).
 */
const JobEntry = (): ReactNode => {
  const record = useRecordContext<BackgroundJobRecord>();
  const translate = useTranslate();
  const createPath = useCreatePath();

  if (record === undefined) {
    return null;
  }

  const state = jobStateOf(record);
  const hasTotal = hasProgressTotal(record);
  const isFailed = state === "failed" || state === "aborted";
  const isActiveRow = state !== "completed" && !isFailed;

  return (
    <Box
      component="li"
      sx={{
        p: 1.5,
        borderLeft: 4,
        borderColor: isFailed
          ? "error.main"
          : state === "completed"
            ? "success.main"
            : "transparent",
        bgcolor: isFailed ? "error.50" : "transparent",
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
        <Box sx={{ pt: 0.25 }} aria-hidden>
          {STATE_ICONS[state]}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
            <Typography
              variant="subtitle2"
              component={Link}
              to={createPath({
                resource: "BackgroundProcess",
                type: "show",
                id: record.id,
              })}
              sx={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}
            >
              {record.description ||
                translate("backgroundActivity.process", {
                  id: String(record.id),
                })}
            </Typography>
            {isActiveRow ? (
              <RelativeDateField
                source="dateCreated"
                sx={{ whiteSpace: "nowrap" }}
              />
            ) : (
              <RelativeDateField
                source="doneAt"
                sx={{ whiteSpace: "nowrap" }}
              />
            )}
          </Stack>
          <Typography
            variant="body2"
            color={isFailed ? "error.main" : "text.secondary"}
            sx={{ overflowWrap: "anywhere" }}
          >
            {isFailed && record.errorSummary
              ? record.errorSummary
              : `${translate(
                  `backgroundActivity.jobCenter.processTypes.${record.processType}`,
                  { _: record.processType },
                )}${record.phase ? ` · ${record.phase}` : ""}`}
          </Typography>
          {isActiveRow && (
            <Box sx={{ mt: 0.5 }}>
              <ProgressField
                source="progress"
                indeterminate={!hasTotal}
                aria-label={translate(
                  hasTotal
                    ? "backgroundActivity.progress"
                    : "backgroundActivity.jobCenter.progressUnknownTotal",
                )}
              />
            </Box>
          )}
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", mt: 0.5 }}
          >
            <ProcessStatusField source="state" />
            {hasTotal && (
              <Typography variant="caption" color="text.secondary">
                {translate("backgroundActivity.steps", {
                  done: record.doneSteps ?? 0,
                  total: record.totalSteps,
                })}
              </Typography>
            )}
            <Box sx={{ flex: 1 }} />
            <AbortBackgroundProcessButton />
          </Stack>
        </Box>
      </Stack>
    </Box>
  );
};

/** one row, read from the record context - the entry point for both the
 *  store-backed tabs and the history panel. The record is normalized before
 *  it is handed to the shared fields: they read the logical state even when
 *  an older api answer only carries the raw status. */
const JobRow = ({
  record,
}: {
  record: BackgroundJobRecord;
}): ReactNode => (
  <RecordContext value={{ ...record, state: jobStateOf(record) }}>
    <JobEntry />
  </RecordContext>
);

const GroupedJobList = ({
  records,
  total,
}: GroupedJobListProps): ReactNode => {
  const translate = useTranslate();
  const { setOpen } = useBackgroundJobCenter();
  const createPath = useCreatePath();
  const groups = groupJobs(records);

  const groupTitle = (group: (typeof groups)[number]): string => {
    const first = group.records[0];
    const related = first?.relatedResource;
    if (related) {
      // the type names the group before the id: a UUID never opens a title
      return `${related.type} · ${related.id.slice(0, 8)}`;
    }
    return translate(
      `backgroundActivity.jobCenter.processTypes.${first?.processType ?? ""}`,
      { _: first?.processType ?? "" },
    );
  };

  return (
    <Box>
      {groups.map((group) => (
        <Box key={group.key}>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ px: 1.5, pt: 1, display: "block" }}
          >
            {groupTitle(group)}
          </Typography>
          <Box component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
            {group.records.map((record) => (
              <JobRow key={String(record.id)} record={record} />
            ))}
          </Box>
          <Divider />
        </Box>
      ))}
      {total > records.length && (
        <Box sx={{ p: 1.5 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {translate("backgroundActivity.jobCenter.truncated", {
              shown: records.length,
              total,
            })}
          </Typography>
          <Button
            component={Link}
            to={createPath({ resource: "BackgroundProcess", type: "list" })}
            size="small"
            onClick={() => setOpen(false)}
          >
            {translate("backgroundActivity.viewAll")}
          </Button>
        </Box>
      )}
    </Box>
  );
};

const CountTile = ({
  label,
  filter,
  icon,
  color,
}: {
  label: string;
  filter: Record<string, string>;
  icon: ReactNode;
  color: "info" | "warning" | "error" | "success";
}): ReactNode => (
  <Card
    variant="outlined"
    sx={{ p: 1, textAlign: "center", borderColor: `${color}.light` }}
  >
    <Stack
      direction="row"
      spacing={0.5}
      sx={{ justifyContent: "center" }}
    >
      {icon}
      <Typography variant="h6" color={`${color}.main`} component="span">
        <Count
          resource="BackgroundProcess"
          filter={filter}
          sort={JOB_COUNT_SORT}
          refetchInterval={COUNTS_POLL_MILLISECONDS}
          variant="inherit"
          component="span"
        />
      </Typography>
    </Stack>
    <Typography variant="caption" color="text.secondary">
      {label}
    </Typography>
  </Card>
);

const HistoryContent = (): ReactNode => {
  const { data = [], isPending, error, refetch } = useListContext<
    BackgroundJobRecord
  >();
  const translate = useTranslate();

  if (isPending) {
    return (
      <Box sx={{ p: 3, textAlign: "center" }}>
        <CircularProgress
          size={24}
          aria-label={translate("ra.message.loading")}
        />
      </Box>
    );
  }
  if (error) {
    return (
      <Alert
        severity="error"
        action={
          <Button onClick={() => void refetch()}>
            {translate("ra.action.refresh")}
          </Button>
        }
        sx={{ m: 1 }}
      >
        {translate("backgroundActivity.loadError")}
      </Alert>
    );
  }
  if (data.length === 0) {
    return (
      <Typography sx={{ p: 3 }} color="text.secondary">
        {translate("backgroundActivity.empty")}
      </Typography>
    );
  }
  return (
    <Box component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
      {data.map((record) => (
        <JobRow key={String(record.id)} record={record} />
      ))}
    </Box>
  );
};

/**
 * The Background Job Drawer (#1206).
 *
 * A responsive right MUI drawer over the approved mockup: summary tiles, the
 * tabs all / running / waiting / failed / history, a search over the bounded
 * store, processes grouped by the resource their work happens on, and an
 * exit into the paginated history screen of the resource.
 *
 * The new parts are the drawer shell, the tabs and the grouping; the tiles
 * and tab labels count through `Count`, the rows reuse the resource's field
 * components and the realtime rows run on `RealtimeListBase`. The shared
 * `Drawer` component could not carry this: its widths and anchors are
 * layout state of the map viewer's `DrawerContext`, which is not mounted in
 * the app shell, and the shared `Tabs` is bound to the closable tab list of
 * that screen.
 */
const JobCenterDrawer = (): ReactNode => {
  const translate = useTranslate();
  const { state, open, setOpen, clearCompleted } = useBackgroundJobCenter();
  const createPath = useCreatePath();
  const [tab, setTab] = useState<JobTab | "history">("all");
  const [search, setSearch] = useState("");

  // the window of the completed tile is fixed for the lifetime of an open
  // drawer: a cutoff which moved per render would make every poll a new query
  const completedFilter = useMemo(() => completedWithinDayFilter(), []);

  const tabLabel = (key: JobTab | "history"): ReactNode => {
    const label = translate(`backgroundActivity.jobCenter.tabs.${key}`);
    const filter =
      key === "running"
        ? JOB_COUNT_FILTERS.running
        : key === "waiting"
          ? JOB_COUNT_FILTERS.waiting
          : key === "failed"
            ? JOB_COUNT_FILTERS.failed
            : undefined;
    if (filter === undefined) {
      // "all" counts the store's window and "history" the whole past - an
      // aggregate number would either be the store's cap or the sum of every
      // process ever; both are answered on the history screen instead
      return label;
    }
    return (
      <>
        {label}{" "}
        <Count
          resource="BackgroundProcess"
          filter={filter}
          sort={JOB_COUNT_SORT}
          refetchInterval={COUNTS_POLL_MILLISECONDS}
          variant="inherit"
          component="span"
        />
      </>
    );
  };

  const visibleFor = (key: JobTab): BackgroundJobRecord[] =>
    visibleJobs(state, key, search);
  const trackedCount = Object.keys(state.jobs).length;
  const completedCount = Object.values(state.jobs).filter(
    (record) => jobStateOf(record) === "completed",
  ).length;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => setOpen(false)}
      slotProps={{
        paper: {
          role: "dialog",
          "aria-label": translate("backgroundActivity.jobCenter.title"),
          sx: { width: { xs: "100%", sm: 460 } },
        },
      }}
    >
      <Box
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: "flex-start", p: 2, pb: 1 }}
        >
          <SyncIcon />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">
              {translate("backgroundActivity.jobCenter.title")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {translate("backgroundActivity.jobCenter.subtitle")}
            </Typography>
          </Box>
          <IconButton
            onClick={() => setOpen(false)}
            aria-label={translate("ra.action.close")}
          >
            <CloseIcon />
          </IconButton>
        </Stack>
        <Box
          sx={{
            px: 2,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))",
            gap: 1,
          }}
        >
          <CountTile
            label={translate("backgroundActivity.jobCenter.tabs.running")}
            filter={JOB_COUNT_FILTERS.running}
            icon={<PlayArrowIcon color="info" fontSize="small" />}
            color="info"
          />
          <CountTile
            label={translate("backgroundActivity.jobCenter.tabs.waiting")}
            filter={JOB_COUNT_FILTERS.waiting}
            icon={<ScheduleIcon color="warning" fontSize="small" />}
            color="warning"
          />
          <CountTile
            label={translate("backgroundActivity.jobCenter.tabs.failed")}
            filter={JOB_COUNT_FILTERS.failed}
            icon={<ErrorOutlinedIcon color="error" fontSize="small" />}
            color="error"
          />
          <CountTile
            label={translate("backgroundActivity.jobCenter.completedInDay")}
            filter={completedFilter}
            icon={<CheckCircleOutlinedIcon color="success" fontSize="small" />}
            color="success"
          />
        </Box>
        <TabContext value={tab}>
          <Box sx={{ px: 1 }}>
            <TabList
              onChange={(_event, value: JobTab | "history") => setTab(value)}
              aria-label={translate("backgroundActivity.jobCenter.title")}
              allowScrollButtonsMobile
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab value="all" label={tabLabel("all")} />
              <Tab value="running" label={tabLabel("running")} />
              <Tab value="waiting" label={tabLabel("waiting")} />
              <Tab value="failed" label={tabLabel("failed")} />
              <Tab value="history" label={tabLabel("history")} />
            </TabList>
          </Box>
          {(["all", "running", "waiting", "failed"] as const).map((key) => {
            const visible = visibleFor(key);
            return (
            <TabPanel key={key} value={key} sx={TAB_PANEL_SX}>
              <Box sx={{ px: 2, pt: 1 }}>
                <TextField
                  size="small"
                  fullWidth
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={translate("backgroundActivity.jobCenter.search")}
                  slotProps={{
                    htmlInput: {
                      "aria-label": translate(
                        "backgroundActivity.jobCenter.search",
                      ),
                    },
                    input: {
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchIcon fontSize="small" />
                        </InputAdornment>
                      ),
                    },
                  }}
                />
              </Box>
              <Box sx={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
                {visible.length === 0 ? (
                  <Typography sx={{ p: 3 }} color="text.secondary">
                    {translate(
                      search === ""
                        ? "backgroundActivity.empty"
                        : "backgroundActivity.jobCenter.searchEmpty",
                    )}
                  </Typography>
                ) : (
                  <GroupedJobList
                    records={visible.slice(0, MAX_RENDERED_ROWS)}
                    total={visible.length}
                  />
                )}
              </Box>
            </TabPanel>
            );
          })}
          <TabPanel value="history" sx={TAB_PANEL_SX}>
            <Box sx={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              <RealtimeListBase
                resource="BackgroundProcess"
                filter={{ status: "completed,aborted" }}
                sort={{ field: "dateCreated", order: "DESC" }}
                perPage={25}
                disableSyncWithLocation
              >
                <HistoryContent />
              </RealtimeListBase>
            </Box>
          </TabPanel>
        </TabContext>
        <Divider />
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: "center",
            justifyContent: "space-between",
            p: 1.5,
          }}
        >
          <Button
            size="small"
            onClick={clearCompleted}
            disabled={completedCount === 0}
          >
            {translate("backgroundActivity.jobCenter.clearCompleted", {
              count: completedCount,
            })}
          </Button>
          <Button
            size="small"
            variant="contained"
            component={Link}
            to={createPath({ resource: "BackgroundProcess", type: "list" })}
            onClick={() => setOpen(false)}
          >
            {translate("backgroundActivity.jobCenter.openHistory")}
          </Button>
        </Stack>
        {trackedCount >= MAX_TRACKED_JOBS && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ px: 1.5, pb: 1 }}
          >
            {translate("backgroundActivity.jobCenter.tracked", {
              tracked: trackedCount,
            })}
          </Typography>
        )}
      </Box>
    </Drawer>
  );
};

export default JobCenterDrawer;
