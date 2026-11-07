import type { ReactNode } from "react";
import {
  DateField,
  DataTable,
  Link,
  ListBase,
  type RaRecord,
  type ShowProps,
  Show,
  useCreatePath,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { Link as RouterLink } from "react-router-dom";

import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Paper,
  Stack,
  Typography,
} from "@mui/material";

import { stateColorOf, UpdateJobStatusChip } from "./UpdateJobState";

/** the message which explains a state of a job, by the code which answers it */
const STATE_MESSAGE = {
  0: "noUpdateNeeded",
  1: "updating",
  2: "reviewRequired",
  3: "error",
  4: "waitingForProcessing",
  5: "updated",
  6: "resume",
} as const;

/** the way back to the catalogue this job was made for */
const CatalogueLink = ({
  catalogue,
  children,
}: {
  catalogue?: RaRecord;
  children: ReactNode;
}) => {
  const createPath = useCreatePath();
  if (!catalogue?.id) return <>{children}</>;
  return (
    <Link to={createPath({ resource: "CatalogueService", id: catalogue.id, type: "show" })}>
      {children}
    </Link>
  );
};

/**
 * The changes this job recorded about the catalogue.
 *
 * An update writes its result into the catalogue through the history of the
 * service, and marks every record it writes with the job which wrote it - the
 * same reason the changelog of a web map service update is read by. What the
 * job did to the metadata records behind the catalogue is answered at the
 * history screens of these records, not here.
 */
const ChangesOfTheJob = ({ jobId }: { jobId: RaRecord["id"] }) => {
  const translate = useTranslate();
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        {translate("resources.CatalogueServiceUpdateJob.changesTitle")}
      </Typography>
      <ListBase
        resource="HistoricalCatalogueService"
        filter={{ history_change_reason: `updatejob_id: ${jobId}` }}
        sort={{ field: "historyDate", order: "DESC" }}
        perPage={10}
        disableSyncWithLocation
      >
        <ChangesTable />
      </ListBase>
    </Paper>
  );
};

/**
 * The rows of the changelog.
 *
 * The empty message stays quiet while the request still answers nothing: an
 * empty changelog of a finished job says something and a not yet answered one
 * does not.
 */
const ChangesTable = () => {
  const { data, isPending } = useListContext();
  const translate = useTranslate();
  if (!isPending && !data?.length)
    return (
      <Typography color="text.secondary">
        {translate("resources.CatalogueServiceUpdateJob.noChanges")}
      </Typography>
    );
  return (
    <DataTable bulkActionButtons={false}>
      <DataTable.Col source="historyDate" label="resources.ChangeLog.historyDate">
        <DateField source="historyDate" showTime />
      </DataTable.Col>
      <DataTable.Col
        source="historyType"
        label="resources.ChangeLog.historyType"
        render={(record: RaRecord) => (
          <Chip
            size="small"
            variant="outlined"
            label={translate(`resources.ChangeLog.${record.historyType}`)}
          />
        )}
      />
    </DataTable>
  );
};

/** one line of the job details: a caption and the answer below it */
const DetailField = ({ label, children }: { label: string; children: ReactNode }) => (
  <Box>
    <Typography variant="caption">{label}</Typography>
    {children}
  </Box>
);

const JobBody = () => {
  const job = useRecordContext();
  const translate = useTranslate();
  const createPath = useCreatePath();
  if (!job) return null;
  const code = job.statusCode as number | undefined;
  const messageKey =
    code !== undefined && code in STATE_MESSAGE
      ? STATE_MESSAGE[code as keyof typeof STATE_MESSAGE]
      : "unknown";
  const ended = Boolean(job.doneAt);
  const fields = "resources.CatalogueServiceUpdateJob.fields";
  const catalogueName =
    job.service?.title ??
    job.service?.stringRepresentation ??
    translate("resources.CatalogueService.singular");
  return (
    <Stack spacing={3} sx={{ p: { xs: 1, md: 3 } }}>
      <Breadcrumbs>
        <CatalogueLink catalogue={job.service}>{catalogueName}</CatalogueLink>
        <Typography variant="body2">
          {translate("resources.CatalogueServiceUpdateJob.job", { id: job.id })}
        </Typography>
      </Breadcrumbs>
      <Box>
        <Stack
          direction="row"
          spacing={2}
          sx={{ flexWrap: "wrap", alignItems: "center" }}
        >
          <Typography variant="h4" sx={{ fontWeight: 600 }}>
            {translate("resources.CatalogueServiceUpdateJob.singular")}
          </Typography>
          <UpdateJobStatusChip />
        </Stack>
        <Typography variant="h6" sx={{ mt: 1 }}>
          <CatalogueLink catalogue={job.service}>
            {catalogueName}
          </CatalogueLink>
        </Typography>
      </Box>
      <Alert severity={stateColorOf(code)}>
        {translate(
          `resources.CatalogueServiceUpdateJob.messages.${messageKey}`,
        )}
      </Alert>
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {translate("resources.CatalogueServiceUpdateJob.jobDetails")}
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={4}>
          <DetailField
            label={translate("resources.CatalogueServiceUpdateJob.job", {
              id: job.id,
            })}
          >
            <Typography>{job.status ?? "—"}</Typography>
          </DetailField>
          <DetailField label={translate(`${fields}.dateCreated`)}>
            <DateField source="dateCreated" record={job} showTime />
          </DetailField>
          <DetailField label={translate(`${fields}.doneAt`)}>
            {ended ? (
              <DateField source="doneAt" record={job} showTime />
            ) : (
              <Typography color="text.secondary">
                {translate("resources.CatalogueServiceUpdateJob.running")}
              </Typography>
            )}
          </DetailField>
          {job.updateCandidate?.id && (
            <DetailField label={translate(`${fields}.updateCandidate`)}>
              <Typography>
                <CatalogueLink catalogue={job.updateCandidate}>
                  {job.updateCandidate?.title ??
                    job.updateCandidate?.stringRepresentation ??
                    translate(
                      "resources.CatalogueServiceUpdateJob.candidate",
                    )}
                </CatalogueLink>
              </Typography>
            </DetailField>
          )}
        </Stack>
      </Paper>
      <ChangesOfTheJob jobId={job.id} />
      <Stack direction="row" spacing={2}>
        <Button
          variant="contained"
          component={RouterLink}
          to={createPath({
            resource: "CatalogueService",
            id: job.service?.id,
            type: "show",
          })}
        >
          {translate("resources.CatalogueServiceUpdateJob.viewCatalogue")}
        </Button>
        <Button
          component={RouterLink}
          to={createPath({
            resource: "CatalogueServiceUpdateJob",
            type: "list",
          })}
        >
          {translate("resources.CatalogueServiceUpdateJob.viewJobs")}
        </Button>
      </Stack>
    </Stack>
  );
};

/**
 * The update job of a catalogue.
 *
 * The update of a catalogue decides about the metadata the catalogue reports
 * about itself, so this screen answers the state of that decision, the moment
 * it ended and what the job wrote while it did - the way the job of a web map
 * service answers its review. An alert which waits for this job leads here.
 */
const ShowCatalogueServiceUpdateJob = (props: ShowProps) => (
  <Show
    {...props}
    actions={false}
    queryOptions={{
      meta: { jsonApiParams: { include: "service,updateCandidate" } },
    }}
  >
    <JobBody />
  </Show>
);

export default ShowCatalogueServiceUpdateJob;
