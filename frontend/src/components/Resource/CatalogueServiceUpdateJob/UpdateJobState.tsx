import type { AlertColor } from "@mui/material/Alert";

import { useRecordContext } from "react-admin";

import { Chip } from "@mui/material";

/**
 * The state of an update job, as the api answers it.
 *
 * The api answers the state twice: `status` names it for a human and
 * `statusCode` answers the very value the job stores
 * (`registry/models/update.py`, `UpdateJobStatusEnum`). The name the api answers
 * is what a screen shows, so nothing here keeps a second list of names; the code
 * is only asked for what a name cannot answer - which colour the state asks for
 * and which sentence explains it.
 */
export const JOB_STATES = {
  noUpdateNeeded: 0,
  updating: 1,
  reviewRequired: 2,
  error: 3,
  waitingForProcessing: 4,
  updated: 5,
  resume: 6,
} as const;

/** the states a job came back from: it decided about itself and waits for nothing */
const FINISHED = new Set<number>([
  JOB_STATES.noUpdateNeeded,
  JOB_STATES.error,
  JOB_STATES.updated,
]);

/** the state an update job of a catalogue explains itself with, by the code which answers it;
 * the ended states reuse the review wording of a web map service update and the states which
 * did not end share one sentence, so only two sentences are this resource's own */
const STATE_MESSAGE: Record<number, string> = {
  [JOB_STATES.noUpdateNeeded]: "updateReview.completedMessage",
  [JOB_STATES.updating]: "resources.CatalogueServiceUpdateJob.notEndedMessage",
  [JOB_STATES.reviewRequired]:
    "resources.CatalogueServiceUpdateJob.reviewRequiredMessage",
  [JOB_STATES.error]: "updateReview.failedMessage",
  [JOB_STATES.waitingForProcessing]:
    "resources.CatalogueServiceUpdateJob.notEndedMessage",
  [JOB_STATES.updated]: "updateReview.completedMessage",
  [JOB_STATES.resume]: "resources.CatalogueServiceUpdateJob.notEndedMessage",
};

/** the name a state of a job is translated by, `null` for a code nothing knows */
export const stateKeyOf = (code?: number): string | null =>
  Object.entries(JOB_STATES).find(([, value]) => value === code)?.[0] ?? null;

/** the sentence which explains a state of a job, `null` for a code nothing knows */
export const messageKeyOf = (code?: number): string | null =>
  code === undefined ? null : STATE_MESSAGE[code] ?? null;

/** how much attention the state of a job asks for */
export const stateColorOf = (code?: number): AlertColor => {
  if (code === JOB_STATES.error) return "error";
  if (code === JOB_STATES.reviewRequired) return "warning";
  if (code !== undefined && FINISHED.has(code)) return "success";
  return "info";
};

/** The state of the update job this screen shows, named by the api and coloured by what it asks for. */
export const UpdateJobStatusChip = () => {
  const job = useRecordContext();
  return (
    <Chip
      size="small"
      color={stateColorOf(job?.statusCode as number | undefined)}
      label={job?.status ?? "—"}
    />
  );
};
