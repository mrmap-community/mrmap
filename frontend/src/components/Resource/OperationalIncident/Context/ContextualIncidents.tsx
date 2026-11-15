import { type ReactNode } from "react";
import { useRecordContext, useResourceContext } from "react-admin";

import { Stack } from "@mui/material";

import IncidentContextBanner from "./IncidentContextBanner";
import IncidentContextHistory from "./IncidentContextHistory";
import useContextualIncidents from "./useContextualIncidents";

export interface ContextualIncidentsProps {
  /** whether the resolved history is shown beside the active banner */
  showHistory?: boolean;
}

/**
 * The operational-incident slot of a detail page (#1322).
 *
 * Dropped into the show of a service, a harvesting run, an update or a
 * monitoring run, it reads the record and resource of that screen from context
 * and shows the active incidents about exactly this record, and - where a viewer
 * is authorised to see history - the resolved ones below it. The incidents come
 * from the same incident api and carry the same identity as the Incident Center
 * of the app bar (#1321), and the links they show go to the permitted service or
 * job the incident names - never to a synthetic job state.
 *
 * It is deliberately silent while the read is pending, while the api cannot be
 * read (its endpoint may not exist until #1319 is merged), and when nothing is
 * active: an idle workflow and a page which has nothing to report look exactly
 * alike, and neither raises an alarm.
 */
const ContextualIncidents = ({
  showHistory = true,
}: ContextualIncidentsProps): ReactNode => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const { active, resolved, isPending, error } = useContextualIncidents({
    resource,
    id: record?.id,
  });

  if (isPending || error || (active.length === 0 && resolved.length === 0)) {
    return null;
  }

  return (
    <Stack spacing={2}>
      <IncidentContextBanner incidents={active} />
      {showHistory && <IncidentContextHistory incidents={resolved} />}
    </Stack>
  );
};

export default ContextualIncidents;
