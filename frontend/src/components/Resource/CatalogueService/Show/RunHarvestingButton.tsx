import PlayArrow from "@mui/icons-material/PlayArrow";
import {
  Button,
  type Identifier,
  useCreate,
  useGetIdentity,
  useNotify,
  useRefresh,
  useResourceDefinition,
} from "react-admin";

const RunHarvestingButton = ({ serviceId }: { serviceId?: Identifier }) => {
  const { hasCreate } = useResourceDefinition({ resource: "HarvestingJob" });
  const { data: identity } = useGetIdentity();
  const [create, { isPending }] = useCreate();
  const notify = useNotify();
  const refresh = useRefresh();
  if (!hasCreate || !identity?.id || serviceId == null) return null;
  return (
    <Button
      label="harvestingSchedules.run"
      variant="contained"
      startIcon={<PlayArrow />}
      disabled={isPending}
      onClick={() =>
        create(
          "HarvestingJob",
          { data: { service: { id: serviceId } } },
          {
            onSuccess: () => {
              notify("harvestingSchedules.queued", { type: "success" });
              refresh();
            },
            onError: () => {
              notify("harvestingSchedules.failed", { type: "error" });
              refresh();
            },
          },
        )
      }
    />
  );
};

export default RunHarvestingButton;
