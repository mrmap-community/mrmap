import StopIcon from "@mui/icons-material/Stop";
import { CircularProgress, IconButton, Tooltip } from "@mui/material";
import {
  useNotify,
  useRecordContext,
  useRefresh,
  useTranslate,
  useUpdate,
} from "react-admin";

/** the statuses a process can still be moved away from */
export const ACTIVE_STATUSES = ["pending", "running"];

/**
 * Stops the work which a background process reports about.
 *
 * A process is stopped by asking it to abort, which is a change of the process
 * and therefore only answered for a user which may change the resource of the
 * process. The api decides who may abort, so the button is shown for every
 * process which did not end yet and the answer of the api is told to the user.
 */
const AbortBackgroundProcessButton = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const notify = useNotify();
  const refresh = useRefresh();
  const [update, { isPending }] = useUpdate();

  if (!record || !ACTIVE_STATUSES.includes(record.status)) {
    return null;
  }

  return (
    <Tooltip title={translate("backgroundActivity.abort")}>
      <IconButton
        size="small"
        aria-label={translate("backgroundActivity.abort")}
        disabled={isPending}
        onClick={() =>
          update(
            "BackgroundProcess",
            { id: record.id, data: { phase: "abort" }, previousData: record },
            {
              mutationMode: "pessimistic",
              onSuccess: () => {
                notify("backgroundActivity.abortAsked", { type: "info" });
                refresh();
              },
              onError: () =>
                notify("backgroundActivity.abortFailed", { type: "error" }),
            },
          )
        }
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
  );
};

export default AbortBackgroundProcessButton;
