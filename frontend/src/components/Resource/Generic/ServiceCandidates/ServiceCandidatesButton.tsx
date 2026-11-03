import { useState, type ReactNode } from "react";
import {
  type RaRecord,
  useRecordContext,
  useResourceContext,
  useTranslate,
} from "react-admin";

import PublicIcon from "@mui/icons-material/Public";
import Button from "@mui/material/Button";

import useOperation from "../../../../jsonapi/hooks/useOperation";
import ServiceCandidatesDialog from "./ServiceCandidatesDialog";

export interface ServiceCandidatesButtonProps {
  /** Record to ask for; the record of the surrounding context by default. */
  record?: RaRecord;
  /** Metadata resource to ask for; the surrounding one by default. */
  resource?: string;
}

/**
 * Opens the candidates of the record of the surrounding context.
 *
 * The button answers nothing when the api does not know the resolution action
 * of the resource, which keeps it off every screen but the two metadata
 * resources and off a backend without them. Discovery is only asked once the
 * dialog is open, so a list of records does not resolve all of them.
 */
export const ServiceCandidatesButton = ({
  record: recordProp,
  resource: resourceProp,
}: ServiceCandidatesButtonProps): ReactNode => {
  const resourceFromContext = useResourceContext();
  const translate = useTranslate();
  const [open, setOpen] = useState(false);
  // like MapViewerButton: the row may pass its record, otherwise the context
  // of the screen answers it
  const contextRecord = useRecordContext({ record: recordProp });
  const resource = resourceProp ?? resourceFromContext;
  const id = (recordProp ?? contextRecord)?.id;
  const supported = Boolean(useOperation(`service_candidates_${resource}`));

  if (!supported || id === undefined || id === null || id === "") return null;

  return (
    <>
      <Button
        color="primary"
        size="small"
        startIcon={<PublicIcon />}
        onClick={() => setOpen(true)}
      >
        {translate("serviceCandidates.button")}
      </Button>
      {/* the dialog is only mounted while it is open: a list of records offers
          the action on every row, and no closed dialog may hold a query */}
      {open && (
        <ServiceCandidatesDialog
          open
          onClose={() => setOpen(false)}
          resource={resource}
          recordId={String(id)}
        />
      )}
    </>
  );
};

export default ServiceCandidatesButton;
