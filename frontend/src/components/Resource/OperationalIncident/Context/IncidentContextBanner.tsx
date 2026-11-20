import { type ReactNode } from "react";
import {
  Link,
  useCreatePath,
  useTranslate,
} from "react-admin";

import { Alert, Stack, Typography } from "@mui/material";

import RelativeDateField from "../../../Field/RelativeDateField";
import {
  incidentDisplayState,
  type IncidentSeverity,
  type OperationalIncidentRecord,
} from "../incidentContract";

/** how many active incidents are spelled out before the rest is summarised -
 *  one banner per incident, never one per retry: the api already folded the
 *  retries of an incident into its `occurrenceCount` (#1322) */
const MAX_BANNERS = 3;

/** which of the two severities reads as urgent to assistive technology */
const alertRole = (severity: IncidentSeverity): "alert" | "status" =>
  severity === "error" ? "alert" : "status";

/** the accessible name of the severity, so colour is never the only signal */
const SEVERITY_WORD: Record<IncidentSeverity, string> = {
  error: "error",
  warning: "warning",
};

export interface IncidentContextBannerProps {
  /** the active incidents about this record, most severe first */
  incidents: OperationalIncidentRecord[];
}

/** the safe, redacted body of one incident, with its retry and count metadata */
const IncidentLine = ({
  incident,
}: {
  incident: OperationalIncidentRecord;
}): ReactNode => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const source = translate(`contextualIncidents.sources.${incident.source}`, {
    _: incident.source,
  });
  const state = translate(
    `contextualIncidents.states.${incidentDisplayState(incident)}`,
  );
  const severity = translate(
    `serviceAlerts.${SEVERITY_WORD[incident.severity]}`,
  );
  // the retry state is answered only when it is known; a count of zero is
  // what the reported operation told, not a hidden first attempt
  const hasRetries = incident.retryCount != null && incident.retryCount > 0;
  const hasOccurrence = incident.occurrenceCount > 1;

  return (
    <Stack spacing={0.25}>
      <Typography component="span" variant="body2">
        {/* severity and state are words, so the colour of the alert is never
            the only thing carrying the meaning */}
        <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
          {severity}
        </Typography>
        {` · ${source} · ${state}`}
      </Typography>
      <Typography component="span" variant="body2">
        {incident.summary}
      </Typography>
      {(hasRetries || incident.retryScheduledUntil) && (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
          {hasRetries && (
            <Typography component="span" variant="caption" color="text.secondary">
              {translate("contextualIncidents.retry", {
                smart_count: incident.retryCount as number,
              })}
            </Typography>
          )}
          {incident.retryScheduledUntil && (
            <Typography component="span" variant="caption" color="text.secondary">
              {translate("contextualIncidents.nextAttempt")}:
            </Typography>
          )}
          {incident.retryScheduledUntil && (
            <RelativeDateField source="retryScheduledUntil" record={incident} />
          )}
        </Stack>
      )}
      {hasOccurrence && (
        <Typography component="span" variant="caption" color="text.secondary">
          {translate("contextualIncidents.occurrences", {
            smart_count: incident.occurrenceCount,
          })}
        </Typography>
      )}
      {incident.affectedResource && (
        // the destination is the resource the api itself named for this
        // incident - answered for the incidents of resources this reader may
        // view alone (#1319), so the show view of the answered pair is always
        // open to him; a system incident names no resource and gets no link,
        // and the client never derives a destination it was not given
        <Link
          to={createPath({
            resource: incident.affectedResource.type,
            type: "show",
            id: incident.affectedResource.id,
          })}
        >
          <Typography component="span" variant="caption">
            {translate("contextualIncidents.viewDetails")}
          </Typography>
        </Link>
      )}
    </Stack>
  );
};

/**
 * The concise active-incident banner of a detail page (#1322).
 *
 * One line per active incident about the record of the screen - never one per
 * retry, because the api has already folded the retries into the count - most
 * severe first. It carries the safe summary, the lifecycle state, the retry
 * progress when it is known, and the one link the api answered. When there is
 * nothing active it renders nothing: an idle workflow shows no alarming state.
 *
 * The words and the link are the same incident identity the Incident Center of
 * the app bar (#1321) shows, so the banner and the center never disagree about
 * what is wrong with this record.
 */
const IncidentContextBanner = ({
  incidents,
}: IncidentContextBannerProps): ReactNode => {
  const translate = useTranslate();
  if (incidents.length === 0) return null;

  const shown = incidents.slice(0, MAX_BANNERS);
  const remaining = incidents.length - shown.length;

  return (
    <Stack spacing={1} aria-label={translate("contextualIncidents.activeLabel")}>
      {shown.map((incident) => (
        <Alert
          key={String(incident.id)}
          severity={incident.severity}
          role={alertRole(incident.severity)}
          variant="standard"
          sx={{ py: 0.75 }}
        >
          <IncidentLine incident={incident} />
        </Alert>
      ))}
      {remaining > 0 && (
        <Typography variant="caption" color="text.secondary">
          {translate("contextualIncidents.moreActive", {
            smart_count: remaining,
          })}
        </Typography>
      )}
    </Stack>
  );
};

export default IncidentContextBanner;
