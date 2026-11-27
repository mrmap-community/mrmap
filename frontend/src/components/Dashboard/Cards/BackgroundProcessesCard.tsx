import { type ReactNode } from "react";
import { Link, RecordContext, useCreatePath, useTranslate } from "react-admin";

import {
  Alert,
  Box,
  Chip,
  LinearProgress,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  type TableCellProps,
} from "@mui/material";

import RelativeDateField from "../../Field/RelativeDateField";
import SimpleCard from "../../MUI/SimpleCard";
import { useBackgroundJobCenter } from "../../Resource/BackgroundProcess/JobCenter/BackgroundJobCenterContext";
import { JOB_COUNT_FILTERS } from "../../Resource/BackgroundProcess/JobCenter/counts";
import {
  FAILED_STATES,
  hasProgressTotal,
  isMovingJob,
  isWaitingJob,
  jobStateOf,
  overviewRows,
  processesAnswer,
  type BackgroundJobRecord,
  type ProcessesAnswer,
} from "../../Resource/BackgroundProcess/JobCenter/jobStore";
import ProcessStatusField from "../../Resource/BackgroundProcess/ProcessStatusField";

/** the rows the table answers at most: a compact panel of the bottom row of the
 *  mockup is read by its exceptions, the complete history answers on the list
 *  screen of the resource, which the card links to (#1815) */
export const MAX_ROWS = 6;

/** the wording of the answer of the whole card: one sentence which says what the
 *  table below it can and cannot tell */
const SCOPE_KEYS: Record<ProcessesAnswer, string> = {
  loading: "dashboard.backgroundProcesses.scope.loading",
  forbidden: "dashboard.backgroundProcesses.scope.forbidden",
  error: "dashboard.backgroundProcesses.scope.error",
  partial: "dashboard.backgroundProcesses.scope.partial",
  empty: "dashboard.backgroundProcesses.scope.empty",
  running: "dashboard.backgroundProcesses.scope.running",
  waiting: "dashboard.backgroundProcesses.scope.waiting",
  history: "dashboard.backgroundProcesses.scope.history",
};

/** the answers which are about the read and not about the work: they replace the
 *  table, because rows of a read which never happened would be rows of nothing */
const UNANSWERED: ProcessesAnswer[] = [
  "loading",
  "forbidden",
  "error",
  "partial",
];

/** the color of the sentence which replaces a table the card cannot answer: a
 *  broken api is an error, a half read answer a warning, a refused read plain
 *  information - the caller is not at fault for a permission it never had */
const severityOf = (answer: ProcessesAnswer): "info" | "warning" | "error" =>
  answer === "error" ? "error" : answer === "partial" ? "warning" : "info";

/** the columns of the compact table, in the order the mockup reads them */
const COLUMNS: { key: string; align: TableCellProps["align"] }[] = [
  { key: "dashboard.backgroundProcesses.type", align: "left" },
  { key: "dashboard.backgroundProcesses.status", align: "center" },
  { key: "dashboard.backgroundProcesses.started", align: "right" },
  { key: "dashboard.backgroundProcesses.progress", align: "left" },
];

/**
 * The progress of one process, and nothing which is not known.
 *
 * A percentage answers only when the process reports one *and* a sealed total of
 * steps, because that pair is the authoritative denominator of the run (#1207,
 * #1259). Work which moves without one answers a moving bar and the word
 * "unknown" - `ProgressField` cannot answer that word, because its determinate
 * branch always prints a percentage and inventing one is what #1207 forbids.
 * Decided work which reported nothing answers the word and no bar.
 */
const ProgressCell = ({
  record,
}: {
  record: BackgroundJobRecord;
}): ReactNode => {
  const translate = useTranslate();
  const reported =
    typeof record.progress === "number" && Number.isFinite(record.progress);
  if (reported && hasProgressTotal(record)) {
    const value = Math.max(
      0,
      Math.min(100, Math.round(record.progress as number)),
    );
    return (
      <Box
        sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 96 }}
      >
        <LinearProgress
          variant="determinate"
          value={value}
          aria-label={translate("backgroundActivity.progress")}
          sx={{ flex: 1, height: 6, borderRadius: 1 }}
        />
        <Typography variant="caption" color="text.secondary">
          {`${value}%`}
        </Typography>
      </Box>
    );
  }
  if (isMovingJob(record)) {
    return (
      <Box
        sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 96 }}
      >
        <LinearProgress
          variant="indeterminate"
          aria-label={translate(
            "backgroundActivity.jobCenter.progressUnknownTotal",
          )}
          sx={{ flex: 1, height: 6, borderRadius: 1 }}
        />
        <Typography variant="caption" color="text.secondary">
          {translate("dashboard.backgroundProcesses.unknown")}
        </Typography>
      </Box>
    );
  }
  return (
    <Typography variant="caption" color="text.secondary">
      {translate("dashboard.backgroundProcesses.notReported")}
    </Typography>
  );
};

/** the moment of the row: the start of the work which moves, the decision of the
 *  work which decided, and the word of a process which names neither */
const MomentCell = ({ record }: { record: BackgroundJobRecord }): ReactNode => {
  const translate = useTranslate();
  const emptyText = translate(
    isWaitingJob(record)
      ? "dashboard.backgroundProcesses.notStarted"
      : "dashboard.backgroundProcesses.noMoment",
  );
  return (
    <RelativeDateField
      source={isMovingJob(record) ? "dateCreated" : "doneAt"}
      emptyText={
        <Typography variant="caption" color="text.secondary">
          {emptyText}
        </Typography>
      }
    />
  );
};

/** one row: the process, its state, its moment and its progress - every field
 *  read from the record context by the shared fields of the resource, so the
 *  words and the colors of a process are the words and colors of the drawer and
 *  of the list screen and never a second reading of them */
const ProcessRow = ({
  record,
  isHistory,
}: {
  record: BackgroundJobRecord;
  /** whether the row came from the window of recently decided processes, which
   *  is history the administrator did not watch happen - its failures are
   *  therefore never read as live ones (#1815) */
  isHistory: boolean;
}): ReactNode => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const kind = translate(
    `backgroundActivity.jobCenter.processTypes.${record.processType}`,
    { _: record.processType },
  );
  const isFailed = FAILED_STATES.includes(jobStateOf(record));
  return (
    <RecordContext value={{ ...record, state: jobStateOf(record) }}>
      <TableRow>
        <TableCell sx={{ py: 0.5 }} title={record.errorSummary ?? undefined}>
          <Typography
            variant="body2"
            component={Link}
            to={createPath({
              resource: "BackgroundProcess",
              type: "show",
              id: record.id,
            })}
            sx={{ display: "block", overflowWrap: "anywhere" }}
          >
            {record.description ||
              translate("backgroundActivity.process", {
                id: String(record.id),
              })}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {kind}
          </Typography>
        </TableCell>
        <TableCell sx={{ py: 0.5 }} align="center">
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 0.25,
            }}
          >
            <ProcessStatusField source="state" />
            {isHistory && (
              <Typography variant="caption" color="text.secondary">
                {translate(
                  isFailed
                    ? "dashboard.backgroundProcesses.failedBefore"
                    : "dashboard.backgroundProcesses.decidedBefore",
                )}
              </Typography>
            )}
          </Box>
        </TableCell>
        <TableCell sx={{ py: 0.5 }} align="right">
          <MomentCell record={record} />
        </TableCell>
        <TableCell sx={{ py: 0.5 }}>
          <ProgressCell record={record} />
        </TableCell>
      </TableRow>
    </RecordContext>
  );
};

/**
 * The work the deployment is doing, in the bottom-right of the dashboard.
 *
 * One compact table of the processes which did not end yet, with the recently
 * decided work behind them: the kind of the process, its state, the moment it
 * started and its progress. The rows answer what an administrator can still act
 * upon first, because a panel of a handful of rows is read by its exceptions.
 *
 * It asks nothing of its own. The processes come from the store of the Background
 * Job Center, which the layout mounts and the realtime bus feeds (#1205, #1461),
 * so the dashboard neither opens a third window onto the same records - the
 * queues card counts them (#1816) and the app bar counts them (#1206) - nor
 * polls a second time beside the fallback poll of that store. The rows are a
 * bounded view onto those two windows and say so beside their link to the
 * complete list.
 *
 * Every answer is distinguished from the others and none of them earns a success
 * word it did not read: work which runs is not work which waits, the work which
 * decided recently is history and never a live failure, and a store which is
 * still loading, which the caller may not read (#1803, #1804), whose api failed,
 * or of which only one window could be read answers itself instead of an empty
 * table. No list controller is mounted for it, so a refused read keeps the
 * administrator on the dashboard instead of navigating the screen away, and no
 * percentage is invented for a run which does not know its denominator.
 */
const BackgroundProcessesCard = (): ReactNode => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const { state, windows, totals, hydrated } = useBackgroundJobCenter();

  // the work of the deployment is operator data behind the session (#833):
  // without one the store is never hydrated and the panel which cannot answer
  // anything answers nothing at all
  if (!hydrated) return null;

  const answer = processesAnswer([windows.active, windows.recent]);
  const unanswered = UNANSWERED.includes(answer);
  const rows = overviewRows(state, MAX_ROWS);
  const decidedIds = new Set(
    windows.recent.records.map((record) => String(record.id)),
  );
  const failedLive = rows.filter(
    (record) =>
      FAILED_STATES.includes(jobStateOf(record)) &&
      !decidedIds.has(String(record.id)),
  ).length;
  const known =
    totals.active !== undefined && totals.recent !== undefined
      ? totals.active + totals.recent
      : undefined;
  const listTo = (filter?: Record<string, string>) => ({
    pathname: createPath({ resource: "BackgroundProcess", type: "list" }),
    search: filter ? `filter=${JSON.stringify(filter)}` : undefined,
  });

  return (
    <SimpleCard
      title={
        <Typography component="h2" variant="subtitle2" noWrap>
          {translate("dashboard.backgroundProcesses.title")}
        </Typography>
      }
      subheader={translate(SCOPE_KEYS[answer])}
      cardProps={{
        variant: "outlined",
        sx: { minWidth: 0, boxShadow: "none", borderRadius: 2 },
      }}
      headerProps={{
        sx: { alignItems: "center", minHeight: 40, px: 1.5, py: 0.25 },
      }}
      contentProps={{
        sx: { px: 0.5, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } },
      }}
      divider={false}
      footer={
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            flexWrap: "wrap",
            rowGap: 0.5,
            px: 1.5,
          }}
        >
          {answer === "empty" && (
            <Chip
              size="small"
              variant="outlined"
              color="default"
              label={translate("dashboard.backgroundProcesses.none")}
            />
          )}
          {failedLive > 0 && (
            <Chip
              size="small"
              variant="outlined"
              color="error"
              component={Link}
              to={listTo(JOB_COUNT_FILTERS.failed)}
              label={translate("dashboard.backgroundProcesses.justFailed", {
                count: failedLive,
              })}
            />
          )}
          {answer === "partial" && (
            <Chip
              size="small"
              variant="outlined"
              color="warning"
              label={translate("dashboard.backgroundProcesses.partialBadge")}
            />
          )}
          <Box sx={{ flex: 1 }} />
          {known !== undefined && rows.length < known && (
            <Typography variant="caption" color="text.secondary">
              {translate("dashboard.backgroundProcesses.bounded", {
                shown: rows.length,
                total: known,
              })}
            </Typography>
          )}
          <Typography variant="body2">
            <Link to={listTo()}>{translate("backgroundActivity.viewAll")}</Link>
          </Typography>
        </Box>
      }
      footerProps={{ sx: { px: 0, py: 0.75, minHeight: 40 } }}
    >
      {answer === "loading" ? (
        <Box sx={{ px: 1, py: 0.5 }}>
          <Skeleton variant="text" width="55%" />
          <Skeleton variant="text" width="80%" />
        </Box>
      ) : unanswered ? (
        <Alert
          severity={severityOf(answer)}
          variant="outlined"
          role="status"
          sx={{ my: 0.5, mx: 1, py: 0.25 }}
        >
          {translate(SCOPE_KEYS[answer])}
        </Alert>
      ) : rows.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          role="status"
          sx={{ px: 1, py: 1 }}
        >
          {translate("backgroundActivity.empty")}
        </Typography>
      ) : (
        <TableContainer sx={{ maxHeight: 216 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {COLUMNS.map((column) => (
                  <TableCell
                    key={column.key}
                    align={column.align}
                    sx={{ py: 0.25, fontWeight: 600 }}
                  >
                    {translate(column.key)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((record) => (
                <ProcessRow
                  key={String(record.id)}
                  record={record}
                  isHistory={decidedIds.has(String(record.id))}
                />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </SimpleCard>
  );
};

export default BackgroundProcessesCard;
