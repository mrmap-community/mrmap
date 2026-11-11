import { useState } from "react";
import {
  Button,
  useNotify,
  useRecordContext,
  useRefresh,
  useResourceDefinition,
  useTranslate,
  useUpdate,
} from "react-admin";

import StopIcon from "@mui/icons-material/Stop";
import {
  CircularProgress,
  IconButton,
  Tooltip,
  Typography,
} from "@mui/material";

import Dialog from "../../Dialog/Dialog";
import DialogHeader from "../../Dialog/DialogHeader";

/**
 * The phase which asks a running job to stop itself. The show screen of a run
 * sends the very same phase (`HarvestingJobActions.tsx`), so a stop means the
 * same thing wherever it is asked for (registry/enums/harvesting.py).
 */
export const ABORT_PHASE = 4711;

/**
 * Stops the harvesting run of the record the caller provides the context of.
 *
 * Nothing is deleted: the run is asked to abort, so what it already stored
 * stays stored. The button belongs to a row whose run did not end, because an
 * ended run has nothing left to stop, and it is only rendered for a caller the
 * schema lets change the resource. As on the show screen the api still decides
 * about the single run, and its answer is told to the user.
 */
const StopHarvestingJobButton = () => {
  const record = useRecordContext();
  const { hasEdit } = useResourceDefinition({ resource: "HarvestingJob" });
  const translate = useTranslate();
  const notify = useNotify();
  const refresh = useRefresh();
  const [update, { isPending }] = useUpdate();
  const [asking, setAsking] = useState(false);

  if (!record || record.doneAt || !hasEdit) {
    return null;
  }

  const close = () => {
    if (!isPending) setAsking(false);
  };

  const stop = async () => {
    try {
      await update(
        "HarvestingJob",
        {
          id: record.id,
          data: { phase: ABORT_PHASE },
          previousData: record,
        },
        { mutationMode: "pessimistic", returnPromise: true },
      );
      notify("harvestRun.list.stopAsked", { type: "info" });
      refresh();
      setAsking(false);
    } catch {
      notify("harvestRun.stopFailed", { type: "error" });
    }
  };

  return (
    <>
      <Tooltip title={translate("harvestRun.stop")}>
        <IconButton
          size="small"
          aria-label={translate("harvestRun.stop")}
          disabled={isPending}
          onClick={() => setAsking(true)}
        >
          {isPending ? (
            <CircularProgress
              size={16}
              aria-label={translate("ra.message.saving")}
            />
          ) : (
            <StopIcon fontSize="small" />
          )}
        </IconButton>
      </Tooltip>
      {asking && (
        <Dialog
          open
          onClose={close}
          maxWidth="xs"
          title={
            <DialogHeader onClose={close}>
              {translate("harvestRun.list.stopConfirmTitle")}
            </DialogHeader>
          }
          actions={
            <>
              <Button
                label="ra.action.cancel"
                onClick={close}
                disabled={isPending}
              />
              <Button
                label="harvestRun.stop"
                variant="contained"
                color="warning"
                onClick={stop}
                disabled={isPending}
                startIcon={<StopIcon />}
              />
            </>
          }
        >
          <Typography>
            {translate("harvestRun.list.stopConfirmContent")}
          </Typography>
        </Dialog>
      )}
    </>
  );
};

export default StopHarvestingJobButton;
