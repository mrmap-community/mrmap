import PowerIcon from "@mui/icons-material/Power";
import PowerOffIcon from "@mui/icons-material/PowerOff";
import {
  Button,
  useNotify,
  useRecordContext,
  useRefresh,
  useResourceContext,
  useUpdate,
} from "react-admin";
import useOperation from "../../../../jsonapi/hooks/useOperation";

/**
 * Turns the availability of a registered service on and off.
 *
 * A deactivated service is not answered by the Mr. Map proxy, so neither the
 * preview image nor the live preview of such a service can be delivered. The
 * button is offered for every service which the api can update at all; which
 * user may change the activation is decided by the api and a refused request is
 * told to the user.
 */
const ActivateServiceButton = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const notify = useNotify();
  const refresh = useRefresh();
  const [update, { isPending }] = useUpdate();
  // the activation is only adjustable as long as the api offers the update
  const canUpdate = Boolean(useOperation(`partial_update_${resource}`));
  // and for records which report about their activation
  const isActive =
    typeof record?.isActive === "boolean" ? record.isActive : undefined;

  if (!record || isActive === undefined || !canUpdate) return null;

  return (
    <Button
      variant="outlined"
      color={isActive ? "warning" : "success"}
      startIcon={isActive ? <PowerOffIcon /> : <PowerIcon />}
      label={isActive ? "serviceShow.deactivate" : "serviceShow.activate"}
      disabled={isPending}
      onClick={() =>
        update(
          resource,
          {
            id: record.id,
            data: { isActive: !isActive },
            previousData: record,
          },
          {
            mutationMode: "pessimistic",
            onSuccess: () => {
              notify(
                isActive
                  ? "serviceShow.deactivated"
                  : "serviceShow.activated",
                { type: "success" },
              );
              // the service and the preview images of it are answered differently now
              void refresh();
            },
            onError: () =>
              notify("serviceShow.activationFailed", { type: "error" }),
          },
        )
      }
    />
  );
};

export default ActivateServiceButton;