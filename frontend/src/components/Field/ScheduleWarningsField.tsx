import { type ReactNode, useId, useState } from "react";
import {
  Link,
  type RaRecord,
  useCreatePath,
  useRecordContext,
  useResourceContext,
  useTranslate,
} from "react-admin";

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { ButtonBase, Popover, Stack, Typography } from "@mui/material";

import RelativeDateField from "./RelativeDateField";

/**
 * One schedule warning as the api answers it (#1332).
 *
 * The keys mirror the stable codes and safe message parameters which
 * `registry.querys.schedule_warnings` answers - the same vocabulary the
 * draft preview of #1327 uses - so the codes are typed apart here while the
 * optional parameters simply answer nothing they did not decide.
 */
export interface ScheduleWarning {
  code:
    | "schedule_overdue"
    | "schedule_too_tight"
    | "insufficient_evidence"
    | "schedule_expired";
  severity: "warning" | "info";
  interval?: string | null;
  observedDuration?: string | null;
  sampleCount?: number | null;
  lastDoneAt?: string | null;
  expectedAt?: string | null;
  expiredAt?: string | null;
  unknownReason?: string | null;
  computedAt?: string | null;
}

const icons: Record<ScheduleWarning["severity"], ReactNode> = {
  warning: <WarningAmberIcon fontSize="small" color="warning" />,
  info: <InfoOutlinedIcon fontSize="small" color="action" />,
};

/** the moment-evidence of one warning, named and read relatively (#1332) */
const MomentLine = ({
  labelKey,
  warning,
  source,
}: {
  labelKey: string;
  warning: ScheduleWarning;
  source: "lastDoneAt" | "expectedAt" | "expiredAt" | "computedAt";
}) => {
  const translate = useTranslate();
  if (warning[source] == null) return null;
  return (
    <Stack direction="row" spacing={1}>
      <Typography variant="body2" color="text.secondary">
        {translate(`scheduleWarnings.${labelKey}`)}
      </Typography>
      <RelativeDateField source={source} record={warning as unknown as RaRecord} />
    </Stack>
  );
};

/** one warning with the parameters which decided it */
const WarningDetails = ({ warning }: { warning: ScheduleWarning }) => {
  const translate = useTranslate();
  const message = (key: string, options?: Record<string, unknown>) =>
    translate(`scheduleWarnings.${key}`, options);
  return (
    <Stack spacing={0.5} sx={{ p: 1.5, maxWidth: 380 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        {icons[warning.severity]}
        <Typography variant="subtitle2">
          {message(`codes.${warning.code}`)}
        </Typography>
      </Stack>
      {warning.interval != null && (
        <Typography variant="body2">
          {message("interval", { value: warning.interval })}
        </Typography>
      )}
      {warning.observedDuration != null && (
        <Typography variant="body2">
          {message("observed", { value: warning.observedDuration })}
        </Typography>
      )}
      {warning.sampleCount != null && (
        <Typography variant="body2" color="text.secondary">
          {message("samples", { smart_count: warning.sampleCount })}
        </Typography>
      )}
      {warning.unknownReason != null && (
        <Typography variant="body2" color="text.secondary">
          {message(`reasons.${warning.unknownReason}`)}
        </Typography>
      )}
      <MomentLine labelKey="lastDone" warning={warning} source="lastDoneAt" />
      <MomentLine labelKey="expectedAt" warning={warning} source="expectedAt" />
      <MomentLine labelKey="expiredAt" warning={warning} source="expiredAt" />
      <MomentLine labelKey="computedAt" warning={warning} source="computedAt" />
    </Stack>
  );
};

export interface ScheduleWarningsFieldProps {
  /** the row to read the warnings at, which is the row of the screen if unset */
  record?: RaRecord;
}

/**
 * The schedule warnings of a saved setting, compact and actionable (#1332).
 *
 * The cell shows the icon and label of the most pressing warning beside the
 * schedule and opens the details of all of them in a popover - interval
 * against observed runtime, the amount of runs which measured it and when -
 * without an edit form and without saving anything. The action leads to the
 * edit of the setting itself, where the schedule is reviewed (#1327 will
 * continue that path as the preview before save).
 *
 * `MouseOverPopover` was considered and did not fit: its popover cannot be
 * entered by pointer (it answers a definition, not an action) and it opens on
 * mouse over only, which cannot carry the action link nor the keyboard access
 * the warnings ask for. `RelativeDateField` is reused for every moment.
 *
 * Nothing answers a row without warnings: a schedule which needs no
 * attention is named nowhere - the rows stay quiet.
 */
const ScheduleWarningsField = ({
  record,
}: ScheduleWarningsFieldProps = {}): ReactNode => {
  const screenRecord = useRecordContext();
  const resource = useResourceContext();
  const createPath = useCreatePath();
  const translate = useTranslate();
  const popoverId = useId();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const row = record ?? screenRecord;
  const warnings: ScheduleWarning[] = Array.isArray(row?.scheduleWarnings)
    ? row.scheduleWarnings
    : [];
  if (warnings.length === 0) return null;

  const first = warnings[0];
  const label = translate(`scheduleWarnings.codes.${first.code}`);
  const editPath =
    resource != null && row?.id != null
      ? createPath({ resource, id: row.id, type: "edit" })
      : undefined;

  return (
    <>
      <ButtonBase
        onClick={(event) => setAnchor(event.currentTarget)}
        aria-describedby={anchor != null ? popoverId : undefined}
        sx={{
          borderRadius: 1,
          px: 0.5,
          py: 0.25,
          gap: 0.5,
          maxWidth: "100%",
        }}
      >
        {icons[first.severity]}
        <Typography
          variant="body2"
          color={first.severity === "warning" ? "warning.main" : "text.secondary"}
          sx={{ whiteSpace: "nowrap" }}
        >
          {label}
          {warnings.length > 1 ? ` (+${warnings.length - 1})` : ""}
        </Typography>
      </ButtonBase>
      <Popover
        id={popoverId}
        open={anchor != null}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{
          paper: {
            sx: (theme) => ({
              border: `1px solid ${theme.palette.divider}`,
            }),
          },
        }}
      >
        <Stack>
          {warnings.map((warning, index) => (
            <WarningDetails
              key={`${warning.code}-${index}`}
              warning={warning}
            />
          ))}
          {editPath != null && (
            <ButtonBase
              component={Link}
              to={editPath}
              onClick={() => setAnchor(null)}
              sx={{ px: 1.5, py: 1, textAlign: "left" }}
            >
              <Typography variant="body2" color="primary">
                {translate("scheduleWarnings.checkSchedule")}
              </Typography>
            </ButtonBase>
          )}
        </Stack>
      </Popover>
    </>
  );
};

export default ScheduleWarningsField;
