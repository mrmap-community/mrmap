import type { AlertColor } from "@mui/material/Alert";

import { useRecordContext, useTranslate } from "react-admin";

import { Chip } from "@mui/material";

/**
 * The state of an update job, as the api answers it.
 *
 * The api answers the state twice: `status` names it for a human and
 * `statusCode` answers the very value the job stores
 * (`registry/models/update.py`, `UpdateJobStatusEnum`). The name the api answers
 * is what a screen shows, so nothing here keeps a second list of names; the code
 * is only asked for what a name cannot answer - which colour, and whether the
 * job waits for something at all.
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

/** the state an update job of a catalogue waits in, by the code which answers it */
const WAITING = {
  [JOB_STATES.updating]: "updating",
  [JOB_STATES.reviewRequired]: "reviewRequired",
  [JOB_STATES.waitingForProcessing]: "waitingForProcessing",
  [JOB_STATES.resume]: "resume",
} as const;

/** the name a state of a job is translated by, `null` for a code nothing knows */
export const stateKeyOf = (code?: number): string | null =>
  Object.entries(JOB_STATES).find(([, value]) => value === code)?.[0] ?? null;

/** how much attention the state of a job asks for */
export const stateColorOf = (code?: number): AlertColor => {
  if (code === JOB_STATES.error) return "error";
  if (code === JOB_STATES.reviewRequired) return "warning";
  if (code !== undefined && FINISHED.has(code)) return "success";
  return "info";
};

/**
 * What a job which did not end yet waits for, in the language of the user.
 *
 * The state of a job is answered by the api in the language of the deployment,
 * so the wait of a job which did not end is named here: the column of a list
 * which asks for the wait has to answer it in the language the screen speaks.
 */
export const waitsFor = (
  job: { statusCode?: number; doneAt?: string | null },
  translate: ReturnType<typeof useTranslate>,
): string | null => {
  if (job.doneAt) return null;
  const key = job.statusCode === undefined
    ? null
    : WAITING[job.statusCode as keyof typeof WAITING];
  return key
    ? translate(`resources.CatalogueServiceUpdateJob.waitsFor.${key}`)
    : null;
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
