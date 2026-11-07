import { useState } from "react";
import {
  type Identifier,
  Button,
  useListContext,
  useNotify,
  useRefresh,
  useResourceDefinition,
  useTranslate,
  useUnselect,
  useUpdate,
} from "react-admin";

import StopIcon from "@mui/icons-material/Stop";
import { LinearProgress, Stack, Typography } from "@mui/material";

import Dialog from "../../Dialog/Dialog";
import DialogHeader from "../../Dialog/DialogHeader";
import { ABORT_PHASE } from "./StopHarvestingJobButton";

/**
 * Stops every selected run of the list with the mutation a single row stops
 * with (`StopHarvestingJobButton.tsx`), and answers how many it stopped.
 *
 * The api has no request which stops several runs at once, so each run is
 * stopped on its own and the ones which refuse - a run which ended in the
 * meantime belongs to them - are named instead of failing the whole selection.
 */
const BulkStopHarvestingJobsButton = () => {
  const { data = [], selectedIds = [] } = useListContext();
  const { hasEdit } = useResourceDefinition({ resource: "HarvestingJob" });
  const translate = useTranslate();
  const notify = useNotify();
  const refresh = useRefresh();
  const unselect = useUnselect("HarvestingJob");
  const [update] = useUpdate();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // a selected run may have ended since it was selected: it has nothing left
  // to stop and is left out of the selection instead of being stopped anyway
  const targetIds = selectedIds.filter(
    (id) => !data.find((record) => record.id === id)?.doneAt,
  );

  const close = () => {
    if (!saving) setOpen(false);
  };

  const stop = async () => {
    if (saving) return;
    setSaving(true);
    const stopped: Identifier[] = [];
    const refused: Identifier[] = [];
    for (const id of targetIds) {
      try {
        await update(
          "HarvestingJob",
          {
            id,
            data: { phase: ABORT_PHASE },
            previousData: data.find((record) => record.id === id) ?? {},
          },
          { mutationMode: "pessimistic", returnPromise: true },
        );
        stopped.push(id);
      } catch {
        refused.push(id);
      }
    }
    setSaving(false);
    unselect(stopped);
    refresh();
    if (stopped.length) {
      notify("harvestRun.list.bulkStopped", {
        type: refused.length ? "warning" : "info",
        messageArgs: { smart_count: stopped.length, count: stopped.length },
      });
    }
    if (refused.length) {
      notify("harvestRun.list.bulkStopRefused", {
        type: stopped.length ? "warning" : "error",
        messageArgs: { ids: refused.join(", ") },
      });
    }
    if (!refused.length) setOpen(false);
  };

  if (!hasEdit || !selectedIds.length) {
    return null;
  }

  return (
    <>
      <Button
        label="harvestRun.list.bulkStopTitle"
        startIcon={<StopIcon />}
        onClick={() => setOpen(true)}
      />
      {open && (
        <Dialog
          open
          onClose={close}
          maxWidth="xs"
          title={
            <DialogHeader onClose={close}>
              {translate("harvestRun.list.bulkStopTitle")}
            </DialogHeader>
          }
          actions={
            <>
              <Button label="ra.action.cancel" onClick={close} disabled={saving} />
              <Button
                label="harvestRun.list.bulkStopTitle"
                variant="contained"
                color="warning"
                onClick={stop}
                disabled={saving || !targetIds.length}
                startIcon={<StopIcon />}
              />
            </>
          }
        >
          <Stack spacing={2}>
            <Typography>
              {translate("harvestRun.list.bulkStopContent", {
                smart_count: targetIds.length,
              })}
            </Typography>
            {saving && <LinearProgress />}
          </Stack>
        </Dialog>
      )}
    </>
  );
};

export default BulkStopHarvestingJobsButton;
