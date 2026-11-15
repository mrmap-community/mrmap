import { type ReactNode } from "react";
import {
  BasenameContextProvider,
  Link,
  useTranslate,
} from "react-admin";

import { Box, Stack, Typography } from "@mui/material";

import RelativeDateField from "../../../Field/RelativeDateField";
import SimpleCard from "../../../MUI/SimpleCard";
import { type OperationalIncidentRecord } from "../incidentContract";

/** newest recovery first: the timeline is ordered by when the incident left the
 *  active set, falling back to its latest activity when no resolution moment is
 *  answered - a stable, testable order independent of severity */
const byNewestActivity = (
  a: OperationalIncidentRecord,
  b: OperationalIncidentRecord,
): number => {
  const at = new Date(a.resolvedAt ?? a.lastOccurrence).getTime();
  const bt = new Date(b.resolvedAt ?? b.lastOccurrence).getTime();
  return bt - at;
};

export interface IncidentContextHistoryProps {
  /** the resolved incidents about this record */
  incidents: OperationalIncidentRecord[];
}

/**
 * The resolved history of the incidents about a record (#1322).
 *
 * Recovery stays inspectable: the incidents which resolved for this record are
 * listed newest-first with the moment they resolved, without implying any
 * present alarm. This is deliberately not the changelog timeline of
 * `Resource/Generic/History`: that component renders created/updated/deleted
 * edits of a record, a shape an operational incident does not have, so it is
 * reused nowhere here; this list reads only the fields the incident api answers.
 *
 * Nothing is rendered when there is no history to show.
 */
const IncidentContextHistory = ({
  incidents,
}: IncidentContextHistoryProps): ReactNode => {
  const translate = useTranslate();
  if (incidents.length === 0) return null;

  const ordered = [...incidents].sort(byNewestActivity);

  return (
    <SimpleCard
      title={translate("contextualIncidents.historyTitle")}
      contentProps={{ sx: { py: 1.5 } }}
    >
      <Stack
        component="ol"
        spacing={1.5}
        sx={{ listStyle: "none", m: 0, p: 0 }}
        aria-label={translate("contextualIncidents.historyLabel")}
      >
        {ordered.map((incident) => {
          const source = translate(
            `contextualIncidents.sources.${incident.sourceType}`,
            { _: incident.sourceType },
          );
          const severity = translate(
            `serviceAlerts.${incident.severity === "error" ? "error" : "warning"}`,
          );
          return (
            <Box component="li" key={String(incident.id)}>
              <Stack spacing={0.25}>
                <Typography component="span" variant="body2">
                  <Typography
                    component="span"
                    variant="body2"
                    sx={{ fontWeight: 600 }}
                  >
                    {severity}
                  </Typography>
                  {` · ${source}`}
                </Typography>
                <Typography component="span" variant="body2">
                  {incident.summary}
                </Typography>
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
                  <Typography
                    component="span"
                    variant="caption"
                    color="text.secondary"
                  >
                    {incident.resolvedAt
                      ? translate("contextualIncidents.resolvedAgo")
                      : translate("contextualIncidents.lastSeen")}
                    :
                  </Typography>
                  <RelativeDateField
                    source={incident.resolvedAt ? "resolvedAt" : "lastOccurrence"}
                    record={incident}
                  />
                  {incident.targetPath && (
                    <BasenameContextProvider basename="">
                      <Link to={incident.targetPath}>
                        <Typography component="span" variant="caption">
                          {translate("contextualIncidents.viewDetails")}
                        </Typography>
                      </Link>
                    </BasenameContextProvider>
                  )}
                </Stack>
              </Stack>
            </Box>
          );
        })}
      </Stack>
    </SimpleCard>
  );
};

export default IncidentContextHistory;
