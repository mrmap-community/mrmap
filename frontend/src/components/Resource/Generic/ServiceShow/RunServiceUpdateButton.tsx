import PlayArrow from "@mui/icons-material/PlayArrow";
import { Alert, Stack } from "@mui/material";
import {
  Button,
  type Identifier,
  ShowButton,
  useCreate,
  useGetIdentity,
  useGetList,
  useNotify,
  useRefresh,
  useResourceDefinition,
  useTranslate,
} from "react-admin";

const RunServiceUpdateButton = ({
  resource,
  serviceId,
}: {
  resource: string;
  serviceId?: Identifier;
}) => {
  const { hasCreate } = useResourceDefinition({ resource });
  const { data: identity } = useGetIdentity();
  const enabled = Boolean(hasCreate && identity?.id && serviceId != null);
  const jobs = useGetList(
    resource,
    {
      filter: { service: serviceId, "doneAt.isnull": true },
      pagination: { page: 1, perPage: 1 },
      sort: { field: "id", order: "DESC" },
    },
    { enabled, refetchInterval: 5_000 },
  );
  const [create, { isPending }] = useCreate();
  const notify = useNotify();
  const refresh = useRefresh();
  const translate = useTranslate();
  const existingJob = jobs.data?.[0];

  if (!enabled) return null;

  return (
    <Stack spacing={1} sx={{ alignItems: "flex-start" }}>
      {jobs.error && (
        <Alert severity="error">{translate("manualUpdate.loadError")}</Alert>
      )}
      {existingJob ? (
        <ShowButton
          resource={resource}
          record={existingJob}
          label="manualUpdate.existing"
        />
      ) : (
        <Button
          label="manualUpdate.run"
          variant="contained"
          startIcon={<PlayArrow />}
          disabled={isPending || jobs.isPending || Boolean(jobs.error)}
          onClick={() =>
            create(
              resource,
              { data: { service: { id: serviceId } } },
              {
                onSuccess: () => {
                  notify("manualUpdate.queued", { type: "success" });
                  refresh();
                },
                onError: () => {
                  notify("manualUpdate.failed", { type: "error" });
                  refresh();
                },
              },
            )
          }
        />
      )}
    </Stack>
  );
};

export default RunServiceUpdateButton;
