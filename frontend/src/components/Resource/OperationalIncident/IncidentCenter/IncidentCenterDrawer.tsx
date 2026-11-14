import { type ReactNode, useMemo, useState } from "react";
import {
  Link,
  RecordContext,
  useRecordContext,
  useTranslate,
} from "react-admin";

import AutorenewIcon from "@mui/icons-material/Autorenew";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CloseIcon from "@mui/icons-material/Close";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import MoreTimeIcon from "@mui/icons-material/MoreTime";
import NotificationImportantIcon from "@mui/icons-material/NotificationImportant";
import TabContext from "@mui/lab/TabContext";
import TabList from "@mui/lab/TabList";
import TabPanel from "@mui/lab/TabPanel";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  Stack,
  Tab,
  Typography,
} from "@mui/material";

import RelativeDateField from "../../../Field/RelativeDateField";
import {
  ACTIVE_INCIDENT_STATES,
  INCIDENT_SEVERITIES,
  isResolvedIncident,
  type IncidentSeverity,
  type IncidentState,
  type OperationalIncidentRecord,
} from "../incidentContract";
import { useIncidentCenter, type IncidentWindow } from "./IncidentCenterContext";

type IncidentTab = "active" | "resolved";

/** a tab panel fills the remaining height of the drawer and scrolls itself;
 *  MUI hides an inactive panel with the `hidden` attribute, which the flex
 *  display below would override - so the hidden case is answered explicitly
 *  (the answer JobCenterDrawer of #1206 found) */
const TAB_PANEL_SX = {
  p: 0,
  flex: 1,
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  "&[hidden]": { display: "none" },
} as const;

const STATE_ICONS: Record<IncidentState, ReactNode> = {
  retrying: <AutorenewIcon color="info" />,
  stalled: <MoreTimeIcon color="warning" />,
  failed: <ErrorOutlinedIcon color="error" />,
  resolved: <CheckCircleOutlinedIcon color="success" />,
};

const STATE_CHIP_COLOR: Record<IncidentState, "info" | "warning" | "error" | "default"> = {
  retrying: "info",
  stalled: "warning",
  failed: "error",
  resolved: "default",
};

/** the moment of `nextRetryAt`, absolute and short: "next attempt at
 *  14:37" is the sentence of the epic (#1104) and the moment is about the
 *  hour of the day, not about its distance to now */
const formatAttemptMoment = (value: string): string => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
};

/**
 * One row of one incident.
 *
 * It reads the incident from the record context and reuses the field
 * components of the Job Center drawer: `RelativeDateField` for the moments
 * (first seen, last seen, resolved) and the same fold-open shape - the first
 * line always carries the safe summary and the most recent moment, the lines
 * below carry the state and source chips, the occurrence count and the retry
 * progress. One record is one row: the server deduplicates recurring
 * incidents by their stable key and answers the folded `occurrenceCount`,
 * so ten retries of one incident sit in this row with an updated count and
 * never in ten rows.
 *
 * The destination: `targetPath` is the path the server answers only for a
 * target this client may open (the ServiceAlert pattern). Without it the row
 * offers no link and no path is ever derived from the code, the source or
 * the id client-side.
 */
const IncidentEntry = (): ReactNode => {
  const record = useRecordContext<OperationalIncidentRecord>();
  const translate = useTranslate();
  const { setOpen } = useIncidentCenter();

  if (record === undefined) {
    return null;
  }

  const resolved = isResolvedIncident(record);
  const isFailure = record.severity === "error";
  // the retry state is built from the pieces it actually answers: an attempt
  // without a known total says "attempt 4", a known next attempt joins them
  const retryLine: string[] = [];
  if (record.retryAttempt !== undefined && record.retryAttempt !== null) {
    retryLine.push(
      translate("incidentCenter.retryAttempt", { attempt: record.retryAttempt }),
    );
    if (record.retryTotal !== undefined && record.retryTotal !== null) {
      retryLine.push(
        translate("incidentCenter.retryOfTotal", { total: record.retryTotal }),
      );
    }
    if (record.nextRetryAt) {
      retryLine.push(
        translate("incidentCenter.nextAttempt", {
          time: formatAttemptMoment(record.nextRetryAt),
        }),
      );
    }
  }

  return (
    <Box
      component="li"
      sx={{
        p: 1.5,
        borderLeft: 4,
        borderColor: isFailure ? "error.main" : "warning.main",
        bgcolor: isFailure ? "error.50" : "transparent",
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
        <Box sx={{ pt: 0.25 }} aria-hidden>
          {STATE_ICONS[record.state]}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "baseline" }}>
            <Typography
              variant="subtitle2"
              sx={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}
            >
              {record.summary}
            </Typography>
            <RelativeDateField
              source="lastOccurrence"
              sx={{ whiteSpace: "nowrap" }}
            />
          </Stack>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap" }}
          >
            <Chip
              size="small"
              color={STATE_CHIP_COLOR[record.state]}
              variant={resolved ? "outlined" : "filled"}
              label={translate(`incidentCenter.states.${record.state}`)}
            />
            <Chip
              size="small"
              variant="outlined"
              label={translate(`incidentCenter.sources.${record.sourceType}`, {
                _: record.sourceType,
              })}
            />
            {record.occurrenceCount > 1 && (
              <Chip
                size="small"
                variant="outlined"
                aria-label={translate("incidentCenter.occurrences", {
                  count: record.occurrenceCount,
                })}
                label={translate("incidentCenter.occurrenceBadge", {
                  count: record.occurrenceCount,
                })}
              />
            )}
          </Stack>
          {retryLine.length > 0 && (
            <Typography variant="body2" color="text.secondary">
              {retryLine.join(" · ")}
            </Typography>
          )}
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ alignItems: "center", mt: 0.25, flexWrap: "wrap" }}
          >
            <Typography variant="caption" color="text.secondary">
              {translate("incidentCenter.firstSeen")}
            </Typography>
            <RelativeDateField source="firstOccurrence" />
            {resolved && (
              <>
                <Typography variant="caption" color="text.secondary">
                  {translate("incidentCenter.resolvedAt")}
                </Typography>
                <RelativeDateField source="resolvedAt" />
              </>
            )}
          </Stack>
          {record.targetPath && (
            <Button
              size="small"
              component={Link}
              to={record.targetPath}
              onClick={() => setOpen(false)}
              sx={{ mt: 0.5 }}
            >
              {translate("incidentCenter.openTarget")}
            </Button>
          )}
        </Box>
      </Stack>
    </Box>
  );
};

/** one row, read from the record context - the record is the api's own,
 *  passed through unchanged: state, severity and the permitted path are
 *  what the server answered */
const IncidentRow = ({
  record,
}: {
  record: OperationalIncidentRecord;
}): ReactNode => (
  <RecordContext value={record}>
    <IncidentEntry />
  </RecordContext>
);

/** one facet of the window filter: chips toggle, the selected one is filled
 *  and carries `aria-pressed`, so the filter is operable without a mouse and
 *  announced as a toggle */
const FacetGroup = ({
  label,
  options,
  selected,
  onSelect,
  wordOf,
}: {
  label: string;
  options: readonly string[];
  selected: string | undefined;
  onSelect: (value: string | undefined) => void;
  wordOf: (value: string) => string;
}): ReactNode => (
  <Stack
    direction="row"
    spacing={0.5}
    sx={{ alignItems: "center", flexWrap: "wrap" }}
  >
    <Typography variant="caption" color="text.secondary">
      {label}
    </Typography>
    {options.map((option) => (
      <Chip
        key={option}
        size="small"
        label={wordOf(option)}
        variant={selected === option ? "filled" : "outlined"}
        aria-pressed={selected === option}
        onClick={() =>
          onSelect(selected === option ? undefined : option)
        }
      />
    ))}
  </Stack>
);

/**
 * The rows of one window with its loading, error and empty answers (#1321):
 * a pending window spins with the loading label of react-admin, a failing
 * one says it and offers the retry of the read, an empty one says what an
 * empty one means - which differs between "nothing asks for attention" and
 * "no resolved incident yet" - and rows beyond the bounded window are
 * named, not hidden.
 */
const WindowContent = ({
  window,
  rows,
  filtered,
  emptyMessage,
}: {
  window: IncidentWindow;
  rows: OperationalIncidentRecord[];
  filtered: boolean;
  emptyMessage: string;
}): ReactNode => {
  const translate = useTranslate();

  if (window.isPending) {
    return (
      <Box sx={{ p: 3, textAlign: "center" }}>
        <CircularProgress
          size={24}
          aria-label={translate("ra.message.loading")}
        />
      </Box>
    );
  }
  if (window.error) {
    return (
      <Alert
        severity="error"
        action={
          <Button onClick={() => void window.refetch()}>
            {translate("ra.action.refresh")}
          </Button>
        }
        sx={{ m: 1 }}
      >
        {translate("incidentCenter.loadError")}
      </Alert>
    );
  }
  if (rows.length === 0) {
    return (
      <Typography sx={{ p: 3 }} color="text.secondary">
        {translate(
          filtered && (window.data?.length ?? 0) > 0
            ? "incidentCenter.emptyFiltered"
            : emptyMessage,
        )}
      </Typography>
    );
  }
  const total = window.total ?? rows.length;
  return (
    <Box>
      <Box component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
        {rows.map((record) => (
          <IncidentRow key={String(record.id)} record={record} />
        ))}
      </Box>
      {!filtered && total > rows.length && (
        <Box sx={{ p: 1.5 }}>
          <Typography variant="body2" color="text.secondary">
            {translate("incidentCenter.truncated", {
              shown: rows.length,
              total,
            })}
          </Typography>
        </Box>
      )}
    </Box>
  );
};

/**
 * The Incident Center Drawer (#1321).
 *
 * A right MUI drawer over the active and the resolved window of the same
 * permitted query the app bar badge reads: the active tab answers the
 * incidents which ask for attention - retrying, suspected stalled, failed -
 * and the resolved tab answers the recoveries which left it, so "recovery
 * removed from the active count, still visible in history" is one drawer
 * wide. Severity, state and source narrow the bounded window client-side;
 * permission is never narrowed client-side because it is never held
 * client-side (#1319 filters it server-side).
 *
 * The new parts are the shell, the two tabs and the facet chips; the rows
 * reuse RelativeDateField like the Job Center drawer does. The shared
 * `Drawer` and `Tabs` components could not carry this for the same reason
 * JobCenterDrawer records: their widths, anchors and tabs are layout state
 * of the map viewer's `DrawerContext`, which is not mounted in the app
 * shell.
 */
const IncidentCenterDrawer = (): ReactNode => {
  const translate = useTranslate();
  const { active, resolved, open, setOpen } = useIncidentCenter();
  const [tab, setTab] = useState<IncidentTab>("active");
  const [severity, setSeverity] = useState<IncidentSeverity | undefined>(
    undefined,
  );
  const [stateFilter, setStateFilter] = useState<IncidentState | undefined>(
    undefined,
  );
  const [source, setSource] = useState<string | undefined>(undefined);

  const activeRecords = useMemo(() => active.data ?? [], [active.data]);
  const resolvedRecords = useMemo(
    () => resolved.data ?? [],
    [resolved.data],
  );
  const tabRecords = tab === "active" ? activeRecords : resolvedRecords;
  // the sources the visible window actually answers - no invented option list
  const sources = useMemo(
    () => [...new Set(tabRecords.map((record) => record.sourceType))],
    [tabRecords],
  );
  // the state facet names states which ask for attention; every resolved row
  // answers "resolved", so the facet is the active window's question - both
  // windows are filtered on their own, so the hidden panel carries its own
  // rows and never an empty stand-in
  const rowsOf = (records: OperationalIncidentRecord[], withState: boolean) =>
    records.filter(
      (record) =>
        (severity === undefined || record.severity === severity) &&
        (source === undefined || record.sourceType === source) &&
        (!withState ||
          stateFilter === undefined ||
          record.state === stateFilter),
    );
  const activeRows = rowsOf(activeRecords, true);
  const resolvedRows = rowsOf(resolvedRecords, false);
  const activeFiltered =
    severity !== undefined || source !== undefined || stateFilter !== undefined;
  const resolvedFiltered = severity !== undefined || source !== undefined;

  const tabLabel = (key: IncidentTab): ReactNode => {
    const window = key === "active" ? active : resolved;
    return (
      <>
        {translate(`incidentCenter.tabs.${key}`)}
        {window.total !== undefined && !window.error
          ? ` ${window.total}`
          : ""}
      </>
    );
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => setOpen(false)}
      slotProps={{
        paper: {
          role: "dialog",
          "aria-label": translate("incidentCenter.title"),
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
          <NotificationImportantIcon />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">
              {translate("incidentCenter.title")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {translate("incidentCenter.subtitle")}
            </Typography>
          </Box>
          <IconButton
            onClick={() => setOpen(false)}
            aria-label={translate("ra.action.close")}
          >
            <CloseIcon />
          </IconButton>
        </Stack>
        <TabContext value={tab}>
          <Box sx={{ px: 1 }}>
            <TabList
              onChange={(_event, value: IncidentTab) => setTab(value)}
              aria-label={translate("incidentCenter.title")}
            >
              <Tab value="active" label={tabLabel("active")} />
              <Tab value="resolved" label={tabLabel("resolved")} />
            </TabList>
          </Box>
          <Box
            sx={{
              px: 2,
              pt: 1,
              pb: 0.5,
              display: "flex",
              flexDirection: "column",
              gap: 0.5,
            }}
          >
            <FacetGroup
              label={translate("incidentCenter.facets.severity")}
              options={INCIDENT_SEVERITIES}
              selected={severity}
              onSelect={setSeverity}
              wordOf={(value) =>
                translate(`incidentCenter.severities.${value}`)
              }
            />
            {tab === "active" && (
              <FacetGroup
                label={translate("incidentCenter.facets.state")}
                options={ACTIVE_INCIDENT_STATES}
                selected={stateFilter}
                onSelect={setStateFilter}
                wordOf={(value) =>
                  translate(`incidentCenter.states.${value}`)
                }
              />
            )}
            <FacetGroup
              label={translate("incidentCenter.facets.source")}
              options={sources}
              selected={source}
              onSelect={setSource}
              wordOf={(value) =>
                translate(`incidentCenter.sources.${value}`, { _: value })
              }
            />
          </Box>
          <TabPanel value="active" sx={TAB_PANEL_SX}>
            <Box sx={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              <WindowContent
                window={active}
                rows={activeRows}
                filtered={activeFiltered}
                emptyMessage="incidentCenter.emptyActive"
              />
            </Box>
          </TabPanel>
          <TabPanel value="resolved" sx={TAB_PANEL_SX}>
            <Box sx={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              <WindowContent
                window={resolved}
                rows={resolvedRows}
                filtered={resolvedFiltered}
                emptyMessage="incidentCenter.emptyResolved"
              />
            </Box>
          </TabPanel>
        </TabContext>
        <Divider />
        <Typography variant="caption" color="text.secondary" sx={{ p: 1.5 }}>
          {translate("incidentCenter.privacyNote")}
        </Typography>
      </Box>
    </Drawer>
  );
};

export default IncidentCenterDrawer;
