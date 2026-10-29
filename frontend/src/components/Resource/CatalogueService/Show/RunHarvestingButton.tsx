import {
  Button,
  type ButtonProps,
  type Identifier,
  useCreate,
  useGetIdentity,
  useNotify,
  useRefresh,
  useResourceDefinition,
} from "react-admin";

import PlayArrow from "@mui/icons-material/PlayArrow";

const RunHarvestingButton = ({
  serviceId,
  variant = "contained",
}: {
  serviceId?: Identifier;
  variant?: ButtonProps["variant"];
}) => {
  const { hasCreate } = useResourceDefinition({ resource: "HarvestingJob" });
  const { data: identity } = useGetIdentity();
  const [create, { isPending }] = useCreate();
  const notify = useNotify();
  const refresh = useRefresh();
  if (!hasCreate || !identity?.id || serviceId == null) return null;
  return (
    <Button
      label="harvestingSchedules.run"
      variant={variant}
      startIcon={<PlayArrow />}
      disabled={isPending}
      onClick={(event) => {
        event.stopPropagation();
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
        );
      }}
    />
  );
};

export default RunHarvestingButton;
