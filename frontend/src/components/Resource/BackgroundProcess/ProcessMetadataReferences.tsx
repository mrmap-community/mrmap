import { type ReactElement } from "react";
import {
  DateField,
  FunctionField,
  TextField,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Box, Chip, Typography } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import TruncatedTextField from "../../Field/TruncatedTextField";
import ListActions from "../../Lists/CustomListActions";
import {
  hasReferencePlan,
  jobStateOf,
  type BackgroundJobRecord,
} from "./JobCenter/jobStore";
import RetryReferenceButton from "./RetryReferenceButton";

/** the work states the api answers for a retained row (#1263) */
const PENDING_STATE = 0;
const LEASED_STATE = 1;
const FAILED_STATE = 2;

/** the states a process is closed in: a retry is never asked of them */
const CLOSED_PROCESS_STATES = ["failed", "aborted"];

/**
 * The references a registration did not store, below its process.
 *
 * A registration keeps a work row for every reference it could not settle
 * (#1263): the pending ones - which a sealed plan counted as skipped - and
 * the failed ones with the kind and the moment of their failure. This panel
 * asks exactly the terms the screen of #1265 pins in behave: the flat
 * collection scoped by the process. The filter key is given in the runtime
 * spelling the behave scenario sends - the camelize mapping does not carry a
 * `__`-lookup into a readable camel word, so this key is the exception to
 * the camelCase the other screens write. The stored references are no rows:
 * the counters of the process answer them, and a row only survives as long
 * as its process.
 *
 * Alternatives considered: `ListTemporaryMdMetadataFile` is fixed to the
 * harvesting question - files with an import error of a run, reached over
 * the run's nested route - and cannot scope by a background process or carry
 * the retry action; `BackgroundProcessLogs` shows the shape a sub-panel of
 * this show screen takes, which this mirrors over the shared `ListGuesser`.
 */
const ProcessMetadataReferences = (): ReactElement | null => {
  const process = useRecordContext();
  const translate = useTranslate();

  if (!process || !hasReferencePlan(process as BackgroundJobRecord)) {
    return null;
  }

  const retryable = !CLOSED_PROCESS_STATES.includes(
    jobStateOf(process as BackgroundJobRecord),
  );
  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" gutterBottom>
        {translate("backgroundActivity.references.title")}
      </Typography>
      <ListGuesser
        resource="TemporaryMdMetadataFile"
        filter={{ background_process__id: process.id }}
        sort={{ field: "requestId", order: "DESC" }}
        storeKey={false}
        refetchInterval={process.doneAt ? false : 5000}
        rowActions={<></>}
        ActionsComponent={(props) => (
          <ListActions {...props} isConfigureable={false} isExportable={false} />
        )}
        columns={[
          <DateField
            key="requestId"
            source="requestId"
            showTime
            label="backgroundActivity.references.request"
          />,
          <TruncatedTextField
            key="requestedUrl"
            source="requestedUrl"
            label="backgroundActivity.references.url"
          />,
          <TextField
            key="describedDisplay"
            source="describedDisplay"
            label="backgroundActivity.references.reference"
          />,
          <FunctionField
            key="state"
            source="state"
            sortable={false}
            label="backgroundActivity.references.state"
            render={(record) => {
              // the collecting words are shared with the harvest table
              // (D6 of #1256): a pending row of a sealed plan is the skipped
              // one, a leased row is a reference being retried right now
              if (record?.state === FAILED_STATE) {
                return (
                  <Chip
                    size="small"
                    color="error"
                    label={translate("harvestRun.collectingStates.failed")}
                  />
                );
              }
              if (record?.state === LEASED_STATE) {
                return (
                  <Chip
                    size="small"
                    color="info"
                    label={translate(
                      "backgroundActivity.references.states.retrying",
                    )}
                  />
                );
              }
              if (record?.state === PENDING_STATE) {
                return (
                  <Chip
                    size="small"
                    color="warning"
                    label={translate("harvestRun.collectingStates.skipped")}
                  />
                );
              }
              return null;
            }}
          />,
          <FunctionField
            key="errorKind"
            source="errorKind"
            sortable={false}
            label="backgroundActivity.references.errorKind"
            render={(record) =>
              typeof record?.errorKind === "string" &&
              record.errorKind !== ""
                ? translate(
                    `backgroundActivity.references.errorKinds.${record.errorKind}`,
                    { _: record.errorKind },
                  )
                : null
            }
          />,
          <DateField
            key="errorAt"
            source="errorAt"
            showTime
            sortable={false}
            label="backgroundActivity.references.errorAt"
          />,
          <FunctionField
            key="retry"
            sortable={false}
            label="backgroundActivity.references.retry"
            render={() => <RetryReferenceButton retryable={retryable} />}
          />,
        ]}
      />
    </Box>
  );
};

export default ProcessMetadataReferences;
