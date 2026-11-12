import {
  Button,
  ListBase,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Alert, Box, Chip, Divider, Stack, Typography } from "@mui/material";

import RelativeDateField from "../../Field/RelativeDateField";

const LOG_TYPE_COLORS = {
  error: "error",
  warning: "warning",
  info: "info",
} as const;

/** the entries the api answers for one process, newest report first */
const LogFeed = () => {
  const { data = [], isPending, error, refetch } = useListContext();
  const translate = useTranslate();

  if (isPending) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("ra.message.loading")}
      </Typography>
    );
  }
  if (error) {
    return (
      <Alert
        severity="error"
        action={
          <Button size="small" onClick={() => void refetch()}>
            {translate("ra.action.refresh")}
          </Button>
        }
      >
        {translate("backgroundActivity.log.loadError")}
      </Alert>
    );
  }
  if (data.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("backgroundActivity.log.empty")}
      </Typography>
    );
  }

  return (
    <Stack divider={<Divider flexItem />}>
      {data.map((log) => (
        <Stack key={log.id} direction="row" spacing={2} sx={{ py: 1 }}>
          <Chip
            size="small"
            color={LOG_TYPE_COLORS[log.logType as keyof typeof LOG_TYPE_COLORS] ?? "default"}
            label={translate(`backgroundActivity.log.type.${log.logType}`, {
              _: log.logType,
            })}
            sx={{ alignSelf: "flex-start", flexShrink: 0 }}
          />
          <Typography
            variant="body2"
            sx={{ flexGrow: 1, whiteSpace: "pre-line", overflowWrap: "anywhere" }}
          >
            {log.description}
          </Typography>
          <RelativeDateField source="date" sx={{ flexShrink: 0 }} />
        </Stack>
      ))}
    </Stack>
  );
};

/**
 * The log entries a background process left behind, below its state.
 *
 * A failure is only inspectable when it survives the notification which
 * announced it: the worker writes what went wrong as log entries of the
 * process (#1177), and this section reads them from the api of the nested
 * route of the shown process, newest first, so the errors of a job remain
 * readable after reload. The api answers only the logs of the processes the
 * user may see and truncates each description, so nothing here is unbounded.
 *
 * Alternatives considered: `ListGuesser` renders a full list screen with its
 * own toolbar and column chooser, which is too much below the fields of a
 * show screen; `PaginatedSingleFieldList` renders one field per row and
 * cannot carry type, text and moment together.
 */
const BackgroundProcessLogs = () => {
  const record = useRecordContext();
  const translate = useTranslate();

  if (!record) {
    return null;
  }

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" gutterBottom>
        {translate("backgroundActivity.log.title")}
      </Typography>
      <ListBase
        resource="BackgroundProcessLog"
        filter={{ backgroundProcess: record.id }}
        sort={{ field: "date", order: "DESC" }}
        perPage={50}
        disableSyncWithLocation
        queryOptions={{
          meta: {
            relatedResource: { resource: "BackgroundProcess", id: record.id },
          },
        }}
      >
        <LogFeed />
      </ListBase>
    </Box>
  );
};

export default BackgroundProcessLogs;
