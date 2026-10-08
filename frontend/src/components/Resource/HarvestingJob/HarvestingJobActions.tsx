import PlayArrow from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import {
  Button,
  PrevNextButtons,
  TopToolbar,
  useCreate,
  useNotify,
  useRecordContext,
  useRedirect,
  useRefresh,
  useUpdate,
} from "react-admin";

const AbortButton = () => {
  const record = useRecordContext();
  const [update, { isPending }] = useUpdate();
  const notify = useNotify();
  const refresh = useRefresh();
  return (
    <Button
      variant="outlined"
      color="warning"
      startIcon={<StopIcon />}
      label="harvestRun.stop"
      disabled={isPending}
      onClick={() =>
        update(
          "HarvestingJob",
          { id: record?.id, data: { phase: 4711 }, previousData: record },
          {
            onSuccess: () => refresh(),
            onError: () => notify("harvestRun.stopFailed", { type: "error" }),
          },
        )
      }
    />
  );
};

const StartAgainButton = () => {
  const record = useRecordContext();
  const [create, { isPending }] = useCreate();
  const redirect = useRedirect();
  const notify = useNotify();
  return (
    <Button
      variant="outlined"
      color="primary"
      startIcon={<PlayArrow />}
      label="harvestRun.restart"
      disabled={isPending}
      onClick={() =>
        create(
          "HarvestingJob",
          {
            data: {
              harvestDatasets: record?.harvestDatasets,
              harvestServices: record?.harvestServices,
              maxStepSize: record?.maxStepSize,
              service: { id: record?.service?.id },
            },
          },
          {
            onSuccess: (data) => redirect("show", "HarvestingJob", data.id),
            onError: () =>
              notify("harvestingSchedules.failed", { type: "error" }),
          },
        )
      }
    />
  );
};

const HarvestingJobActions = () => {
  const record = useRecordContext();
  return (
    <TopToolbar>
      {record?.doneAt ? (
        record.service?.id && <StartAgainButton />
      ) : (
        <AbortButton />
      )}
      <PrevNextButtons
        linkType="show"
        limit={10}
        sort={{ field: "dateCreated", order: "DESC" }}
        queryOptions={{
          meta: { jsonApiParams: { "fields[HarvestingJob]": "id" } },
        }}
        filter={
          record?.service ? { service__id: record.service.id } : undefined
        }
      />
    </TopToolbar>
  );
};

export default HarvestingJobActions;
