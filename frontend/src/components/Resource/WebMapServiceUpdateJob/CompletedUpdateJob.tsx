import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import {
  DataTable,
  DateField,
  FilterForm,
  ListBase,
  Pagination,
  type RaRecord,
  RecordContext,
  SelectInput,
  useCreatePath,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { Link as RouterLink } from "react-router-dom";
import type { HistoryRecord } from "../Generic/History/HistoryTimeline";
import UpdateJobChangeSummary from "./UpdateJobChangeSummary";

interface LayerHistoryRecord extends HistoryRecord {
  title?: string;
  identifier?: string;
  abstract?: string;
}

const valueText = (value: unknown) =>
  value == null
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);

const historyChangeType = (record: LayerHistoryRecord) =>
  record.historyType === "deleted"
    ? "removed"
    : record.historyType === "created" || record.delta == null
      ? "added"
      : record.delta.length
        ? "modified"
        : "unchanged";

const ChangeDetails = () => {
  const record = useRecordContext<LayerHistoryRecord>();
  const translate = useTranslate();
  if (!record) return null;
  // Creation and deletion show the recorded snapshot, rather than a misleading diff.
  const snapshot =
    historyChangeType(record) === "added" || record.historyType === "deleted";
  const fields = snapshot
    ? ["title", "identifier", "abstract"].map((field) => ({
        field,
        old: undefined,
        new: record[field],
      }))
    : (record.delta ?? []);
  return (
    <Stack spacing={2} sx={{ p: 2 }}>
      {fields.map((change) => (
        <Box key={change.field}>
          <Typography variant="subtitle2">
            {translate(`resources.Layer.fields.${change.field}`, {
              _: change.field,
            })}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            {!snapshot && (
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary">
                  {translate("updateReview.before")}
                </Typography>
                <Typography
                  sx={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}
                >
                  {valueText(change.old)}
                </Typography>
              </Box>
            )}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" color="text.secondary">
                {translate(
                  snapshot
                    ? "updateReview.recordedDetails"
                    : "updateReview.after",
                )}
              </Typography>
              <Typography
                sx={{ overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}
              >
                {valueText(change.new)}
              </Typography>
            </Box>
          </Stack>
        </Box>
      ))}
      {!fields.length && (
        <Typography color="text.secondary">
          {translate("updateReview.noFieldChanges")}
        </Typography>
      )}
    </Stack>
  );
};

const ChangesTable = () => {
  const { error, isPending, data, filterValues } = useListContext();
  const translate = useTranslate();
  if (error)
    return (
      <Alert severity="error">
        {translate("updateReview.historyLoadError")}
      </Alert>
    );
  if (!isPending && !data?.length)
    return (
      <Typography sx={{ p: 2 }} color="text.secondary">
        {translate(
          filterValues.change_type
            ? "updateReview.noChanges"
            : "updateReview.noRecordedChanges",
        )}
      </Typography>
    );
  return (
    <>
      <DataTable
        bulkActionButtons={false}
        rowClick="expand"
        expand={<ChangeDetails />}
      >
        <DataTable.Col
          source="title"
          label="resources.Layer.fields.title"
          disableSort
        />
        <DataTable.Col
          source="identifier"
          label="resources.Layer.fields.identifier"
          disableSort
        />
        <DataTable.Col
          label="updateReview.change"
          render={(record: LayerHistoryRecord) => (
            <Chip
              size="small"
              variant="outlined"
              label={translate(`updateReview.${historyChangeType(record)}`)}
            />
          )}
        />
        <DataTable.Col
          source="historyDate"
          label="resources.ChangeLog.historyDate"
        >
          <DateField source="historyDate" showTime />
        </DataTable.Col>
      </DataTable>
      <Pagination rowsPerPageOptions={[10, 25, 50]} />
    </>
  );
};

export default function CompletedUpdateJob({ job }: { job: RaRecord }) {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const failed = job.statusCode === 3;
  return (
    <Stack spacing={3} sx={{ p: { xs: 1, md: 3 } }}>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: "center", flexWrap: "wrap" }}
      >
        <Typography variant="h4" sx={{ fontWeight: 600 }}>
          {translate(
            failed ? "updateReview.failedTitle" : "updateReview.completedTitle",
          )}
        </Typography>
        <Chip color={failed ? "error" : "success"} label={job.status} />
      </Stack>
      <Typography variant="h6">
        {job.service?.title ??
          job.service?.stringRepresentation ??
          translate("updateReview.job", { id: job.id })}
      </Typography>
      <Alert severity={failed ? "error" : "success"}>
        {translate(
          failed
            ? "updateReview.failedMessage"
            : "updateReview.completedMessage",
        )}
      </Alert>
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {translate("updateReview.jobDetails")}
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={4}>
          <Box>
            <Typography variant="caption">
              {translate("updateReview.job", { id: job.id })}
            </Typography>
            <Typography>{job.status}</Typography>
          </Box>
          <Box>
            <Typography variant="caption">
              {translate("updateReview.createdAt")}
            </Typography>
            <DateField source="dateCreated" record={job} showTime />
          </Box>
          <Box>
            <Typography variant="caption">
              {translate("updateReview.finishedAt")}
            </Typography>
            <DateField source="doneAt" record={job} showTime />
          </Box>
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2.5, overflow: "auto" }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {translate("updateReview.changesMade")}
        </Typography>
        <Box sx={{ mb: 2 }}>
          <RecordContext value={job}>
            <UpdateJobChangeSummary/>
          </RecordContext>
        </Box>
        <ListBase
          resource="HistoricalLayer"
          filter={{
            history_change_reason: `updatejob_id: ${job.id}`,
            service: job.service?.id,
          }}
          sort={{ field: "historyDate", order: "DESC" }}
          perPage={10}
          disableSyncWithLocation
        >
          <FilterForm
            filters={[
              <SelectInput
                key="change_type"
                source="change_type"
                label="updateReview.change"
                alwaysOn
                emptyText="updateReview.all"
                choices={["modified", "unchanged", "removed", "added"].map(
                  (id) => ({
                    id,
                    name: `updateReview.${id}`,
                  }),
                )}
              />,
            ]}
          />
          <ChangesTable />
        </ListBase>
      </Paper>
      <Stack direction="row" spacing={2}>
        <Button
          variant="contained"
          component={RouterLink}
          to={createPath({
            resource: "WebMapService",
            id: job.service?.id,
            type: "show",
          })}
        >
          {translate("updateReview.viewService")}
        </Button>
        <Button
          component={RouterLink}
          to={createPath({ resource: "WebMapServiceUpdateJob", type: "list" })}
        >
          {translate("updateReview.backToJobs")}
        </Button>
      </Stack>
    </Stack>
  );
}
