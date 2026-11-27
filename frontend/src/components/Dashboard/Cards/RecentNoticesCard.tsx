import type { Notices, NoticeRow, NoticeSource } from "../dashboardNotices";

import { Link, useCreatePath, useLocaleState, useTranslate } from "react-admin";

import AssignmentLateIcon from "@mui/icons-material/AssignmentLate";
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import SimpleCard from "../../MUI/SimpleCard";
import {
  dashboardNotices,
  NOTICE_WINDOW_DAYS,
  noticeWindow,
} from "../dashboardNotices";
import { useDashboardNotices } from "../useDashboardNotices";

/** the chip color of a notice kind: an alert answers its severity, an audit row
 *  the weight of what it did to the record; an unknown kind stays neutral */
const KIND_COLORS = {
  error: "error",
  warning: "warning",
  created: "success",
  deleted: "error",
  updated: "info",
} as const;

/** the word a kind is answered with: the severities are the words of the alerts,
 *  the history types those of the changelog screens */
const KIND_LABELS = {
  error: "serviceAlerts.error",
  warning: "serviceAlerts.warning",
  created: "historyList.created",
  updated: "historyList.updated",
  deleted: "historyList.deleted",
} as const;

/** the columns of the table, in the order the mockup reads them */
const COLUMNS = [
  "dashboard.notices.columns.time",
  "dashboard.notices.columns.type",
  "dashboard.notices.columns.description",
  "dashboard.notices.columns.target",
] as const;

/** the words beside a source which did not answer; none of them reads as "no
 *  notices of that kind exist", which is the false green this card prevents */
const SOURCE_MESSAGES = {
  loading: "dashboard.notices.loadingSource",
  error: "dashboard.notices.errorSource",
  forbidden: "dashboard.notices.forbiddenSource",
  unsupported: "dashboard.notices.unsupportedSource",
} as const;

type Translate = ReturnType<typeof useTranslate>;

/** the word a resource is answered with: the name the resource registry gives
 *  it, the plural of the inventory cards behind it, the type as the last one */
const resourceName = (translate: Translate, resource: string): string =>
  translate(`resources.${resource}.name`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });

const knownKind = (kind: string): keyof typeof KIND_COLORS | undefined =>
  kind in KIND_COLORS ? (kind as keyof typeof KIND_COLORS) : undefined;

const kindChip = (kind: string, translate: Translate) => {
  const known = knownKind(kind);
  return (
    <Chip
      size="small"
      variant="outlined"
      color={known ? KIND_COLORS[known] : "default"}
      label={translate(known ? KIND_LABELS[known] : "", { _: kind })}
    />
  );
};

/** the fields an audit row changed, phrased as the compact feeds of the record
 *  screens phrase them, so one change is read with one wording (#1687) */
const auditDescription = (row: NoticeRow, translate: Translate): string => {
  const fields = row.delta ?? [];
  // a row whose api answered no field change says exactly that, instead of
  // repeating the word of its type in a second column (#1819)
  if (fields.length === 0) return translate("historyList.noFieldChanges");
  const known = knownKind(row.kind);
  const event = translate(known ? KIND_LABELS[known] : "", { _: row.kind });
  const field = fields[0].field;
  const first = translate(`resources.${row.source}.fields.${field}`, {
    _: translate(`serviceShow.fields.${field}`, { _: field }),
  });
  const changes = fields.length === 1
    ? translate("historyList.fieldChanged", { _: "%{field} changed", field: first })
    : translate("historyList.fieldsChanged", {
      _: "%{field} and %{smart_count} other fields changed",
      field: first,
      smart_count: fields.length - 1,
    });
  return row.kind === "updated" ? changes : `${event} · ${changes}`;
};

/** the description of a row: the message of an alert once it says more than its
 *  category does, the changed fields of an audit row */
const descriptionOf = (row: NoticeRow, translate: Translate): string => {
  if (row.origin === "audit") return auditDescription(row, translate);
  const category = row.category
    ? translate(`serviceAlerts.categories.${row.category}`, { _: row.category })
    : "";
  const message = row.message && row.message !== row.category ? row.message : "";
  // an alert which answered neither a category nor a message is not dressed up
  // with a description the api does not know
  return [category, message].filter(Boolean).join(" — ")
    || translate("dashboard.notices.noDetail");
};

/** the moment of a row in the locale of the screen; a row the api did not date
 *  answers that answer, and never the time of the screen */
const momentOf = (row: NoticeRow, locale: string, translate: Translate): string => {
  if (row.occurredAt === null) {
    return translate("dashboard.notices.noTime", { _: "no date" });
  }
  return new Date(row.occurredAt).toLocaleString(locale === "en" ? "en-GB" : locale, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
};

/** one row of the table: every cell answers a field of the record behind it and
 *  nothing else - the affected record links to itself */
const NoticeRowView = ({ row }: { row: NoticeRow }) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const description = descriptionOf(row, translate);
  return (
    <TableRow>
      <TableCell sx={{ whiteSpace: "nowrap" }}>
        <Typography variant="caption">{momentOf(row, locale, translate)}</Typography>
      </TableCell>
      <TableCell>{kindChip(row.kind, translate)}</TableCell>
      <TableCell>
        <Typography variant="body2" noWrap title={description || undefined}>
          {description}
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2" noWrap title={row.target}>
          <Link to={row.link}>{row.target}</Link>
        </Typography>
      </TableCell>
    </TableRow>
  );
};

/** the answer of the card while it is not rows: each of these states means
 *  something else, so none of them is answered by the absence of the card */
const TableState = ({ notices }: { notices: Notices }) => {
  const translate = useTranslate();
  if (notices.status === "loading") {
    return <LinearProgress aria-label={translate("dashboard.notices.loading")} />;
  }
  if (notices.status === "error") {
    return (
      <Alert severity="error" role="alert">
        {translate("dashboard.notices.loadError")}
      </Alert>
    );
  }
  return (
    <Typography variant="body2" color="text.secondary" role="status">
      {translate(notices.status === "unsupported"
        ? "dashboard.notices.unsupported"
        : "dashboard.notices.empty")}
    </Typography>
  );
};

/** the sources which did not answer, named one by one: a source which is
 *  quietly absent from the table is read as a deployment whose notices of that
 *  kind do not exist (#1816 reads a refused count the same way) */
const UnavailableSources = ({ sources }: { sources: NoticeSource[] }) => {
  const translate = useTranslate();
  const missing = sources.filter((source) => source.status !== "ready");
  return (
    <Stack spacing={0.25}>
      {missing.map((source) => (
        <Typography
          key={source.resource}
          variant="caption"
          color="warning.main"
          role="status"
        >
          {translate(
            SOURCE_MESSAGES[source.status as keyof typeof SOURCE_MESSAGES]
              ?? "dashboard.notices.errorSource",
            { resource: resourceName(translate, source.resource) },
          )}
        </Typography>
      ))}
    </Stack>
  );
};

/** whether a source is an entrance the caller can actually walk through: a
 *  trail the schema does not answer has no `history` route at all and a read
 *  the api refused answers "access denied", so neither is offered (#1804) */
const linkable = (source: NoticeSource): boolean =>
  source.status === "ready" || source.status === "loading";

/** the links to the lists the rows come out of: the table is the entrance to
 *  the alerts and to the changelogs, never a second copy of either screen */
const NoticeLinks = ({ sources }: { sources: NoticeSource[] }) => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const alertsList = createPath({ resource: "ServiceAlert", type: "list" });
  const alerts = sources.find((source) => source.origin === "alert");
  const audited = sources.filter((source) => source.origin === "audit" && linkable(source));
  return (
    <>
      {alerts !== undefined && linkable(alerts) && (
        <Button component={Link} size="small" to={alertsList}>
          {translate("serviceAlerts.viewAll")}
        </Button>
      )}
      {audited.map((source) => (
        <Button
          key={source.resource}
          component={Link}
          size="small"
          to={`/${source.resource}/history`}
        >
          {translate("dashboard.notices.viewHistory", {
            resource: resourceName(translate, source.resource),
          })}
        </Button>
      ))}
    </>
  );
};

/**
 * The recent notices and activity of the deployment, as a compact table (#1819).
 *
 * The rows are the newest notices of the sources the caller may read: the
 * attention of the services and the audit trail of the three resources the
 * dashboard verifies its history over. They are merged by their moment, newest
 * first, over the bounded page each source answered - never summed, never over
 * the whole history, and never with a moment, a message or an affected record
 * the api did not answer. Each row links to the record behind it and the footer
 * links to the lists the rows come out of, so the table is an entrance and not
 * a second copy of those screens. The system health card (#1816) answers the
 * deployment itself beside this; nothing here repeats it.
 *
 * The answers are kept apart, because each of them means something else to an
 * administrator: rows answer rows, a read which is out answers a progress mark,
 * a read the api refused answers an error, sources which did not answer are
 * named beside the rows they are missing from, and a bounded window without a
 * notice answers emptiness. A caller who may read none of the sources sees no
 * card at all and is never redirected away from the dashboard (#1804).
 *
 * The period the rows cover is the window the sources were asked for and is
 * said in the subheader, so a bounded table is never read as the whole activity
 * of the deployment.
 */
const RecentNoticesCard = ({ resources, now }: {
  /** the resources the caller may read, which decide the audited sources */
  resources: string[];
  /** the end of the bounded window, which the caller keeps stable per mount */
  now: number;
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const sources: NoticeSource[] = useDashboardNotices(resources, now);
  const notices = dashboardNotices(sources);
  // a caller who may read none of the sources is answered by the absence of the
  // card: the table is an administrator view and a refusal never redirects
  if (notices.status === "forbidden") return null;

  const dates = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : locale, {
    day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
  });
  const period = noticeWindow(now);
  const day = (value: string) => dates.format(new Date(`${value}T00:00:00Z`));
  const subheader = (
    <Stack spacing={0.25}>
      <Typography variant="caption" color="text.secondary" component="span">
        {translate("dashboard.notices.window", {
          from: day(period.from),
          to: day(period.to),
          days: NOTICE_WINDOW_DAYS,
        })}
      </Typography>
      {notices.status === "ready" && notices.truncated && (
        <Typography variant="caption" color="text.secondary" component="span" role="status">
          {translate("dashboard.notices.truncated", { rows: notices.rows.length })}
        </Typography>
      )}
    </Stack>
  );

  return (
    <SimpleCard
      title={
        <Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.5 }}>
          <AssignmentLateIcon fontSize="small" color="primary" />
          <Typography component="h2" variant="subtitle2">{translate("dashboard.notices.title")}</Typography>
        </Stack>
      }
      subheader={subheader}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2 } }}
      headerProps={{ sx: { alignItems: "flex-start", px: 1.5, pt: 1, pb: 0.5 } }}
      contentProps={{ sx: { p: 0, "&:last-child": { pb: 0 } } }}
      footer={notices.status === "unsupported"
        ? undefined
        : <NoticeLinks sources={sources} />}
      footerProps={{ sx: { flexWrap: "wrap", px: 1, py: 0.5, rowGap: 0.25 } }}
      divider={false}
    >
      {notices.status !== "ready" || notices.rows.length === 0 ? (
        <Box sx={{ px: 1.5, py: 1 }}>
          <TableState notices={notices} />
        </Box>
      ) : (
        <TableContainer>
          <Table size="small" aria-label={translate("dashboard.notices.title")}>
            <TableHead>
              <TableRow>
                {COLUMNS.map((column) => (
                  <TableCell key={column} sx={{ py: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {translate(column)}
                    </Typography>
                  </TableCell>
                ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {notices.rows.map((row) => (
                  <NoticeRowView key={`${row.source}:${row.id}`} row={row} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
      )}
      {notices.status !== "loading" && notices.status !== "unsupported" && (
        <Box sx={{ px: 1.5, pb: 1 }}>
          <UnavailableSources sources={sources} />
        </Box>
      )}
    </SimpleCard>
  );
};

export default RecentNoticesCard;
