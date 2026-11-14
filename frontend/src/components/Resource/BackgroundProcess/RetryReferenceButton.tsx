import {
  useNotify,
  useRecordContext,
  useRefresh,
  useTranslate,
  useUpdate,
} from "react-admin";

import AutorenewIcon from "@mui/icons-material/Autorenew";
import { CircularProgress, IconButton, Tooltip } from "@mui/material";

/** the work state whose row may be asked again: a PENDING reference is not
 *  yet due and a LEASED one is somebody's work right now - only the FAILED
 *  one answers to a new attempt (`registry/enums/harvesting.py`, #1263) */
export const REFERENCE_FAILED_STATE = 2;

export interface RetryReferenceButtonProps {
  /** whether the process behind the row may still take an attempt; a FAILED
   *  or ABORTED process is never reopened, so its panel passes false */
  retryable?: boolean;
}

/**
 * Asks one failed metadata reference of a registration to be fetched again.
 *
 * The retry is a mutation on the work row itself - the same kind of decided
 * write as the abort of a process: the client sets the write-only `retry`
 * flag and the api answers which of its guards accepted, so the button is
 * shown for every failed row whose process may still work and the answer is
 * told to the user (#1265). The row stays where it is with its verdict until
 * the new attempt reports; the pessimistic mutation only refetches, it does
 * not pretend the reference is already collected.
 */
const RetryReferenceButton = ({
  retryable = true,
}: RetryReferenceButtonProps) => {
  const record = useRecordContext();
  const translate = useTranslate();
  const notify = useNotify();
  const refresh = useRefresh();
  const [update, { isPending }] = useUpdate();

  if (!record || !retryable || record.state !== REFERENCE_FAILED_STATE) {
    return null;
  }

  return (
    <Tooltip title={translate("backgroundActivity.references.retry")}>
      <IconButton
        size="small"
        aria-label={translate("backgroundActivity.references.retry")}
        disabled={isPending}
        onClick={() =>
          update(
            "TemporaryMdMetadataFile",
            { id: record.id, data: { retry: true }, previousData: record },
            {
              mutationMode: "pessimistic",
              onSuccess: () => {
                notify("backgroundActivity.references.retryAsked", {
                  type: "info",
                });
                refresh();
              },
              onError: () =>
                notify("backgroundActivity.references.retryFailed", {
                  type: "error",
                }),
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
          <AutorenewIcon fontSize="small" />
        )}
      </IconButton>
    </Tooltip>
  );
};

export default RetryReferenceButton;
