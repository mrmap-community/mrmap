import SimpleCard from "../../../../MUI/SimpleCard";
import {
  Alert,
  alpha,
  type CardHeaderProps,
  Stack,
  Typography,
} from "@mui/material";
import type { PropsWithChildren } from "react";
import {
  CreateButton,
  Loading,
  type RaRecord,
  useCreatePath,
  useGetList,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";

interface RunSetting extends RaRecord {
  enabled: boolean;
  runOverdue: boolean;
}

interface RunHistoryCardProps extends PropsWithChildren {
  resource: string;
  settingsResource: string;
  serviceFilter: string;
  color?: "success" | "warning" | "error";
  getHeader: (
    overdue: boolean,
  ) => Pick<CardHeaderProps, "title" | "subheader" | "action">;
}

const RunHistoryCard = ({
  children,
  resource,
  settingsResource,
  serviceFilter,
  color: statusColor,
  getHeader,
}: RunHistoryCardProps) => {
  const { data, isPending, error } = useListContext();
  const service = useRecordContext();
  const createPath = useCreatePath();
  const translate = useTranslate();
  const message = (key: string) => translate(`resources.${resource}.${key}`);
  const hasRuns = (data?.length ?? 0) > 0;
  const empty = !isPending && !error && data !== undefined && !hasRuns;
  const settings = useGetList<RunSetting>(
    settingsResource,
    {
      filter: { [serviceFilter]: service?.id },
      sort: { field: "id", order: "ASC" },
      pagination: { page: 1, perPage: 1000 },
    },
    {
      enabled: service?.id != null,
      refetchInterval: 30_000,
    },
  );
  const settingsReady =
    !settings.isPending && !settings.error && settings.data !== undefined;
  const noSettings = settingsReady && settings.data?.length === 0;
  const overdue = Boolean(
    settingsReady &&
    settings.data?.some((setting) => setting.enabled && setting.runOverdue),
  );
  const color = overdue ? "warning" : statusColor;
  const emptyMessage = noSettings
    ? "noSetting"
    : overdue
      ? "runOverdue"
      : settings.data?.some((setting) => setting.enabled)
        ? "waitingForFirstRun"
        : "settingsDisabled";

  return (
    <SimpleCard
      divider={false}
      cardProps={{
        variant: "outlined",
        sx: {
          width: "100%",
          minWidth: 0,
          flex: 1,
          border: 1,
          borderColor: color ? `${color}.main` : "divider",
        },
      }}
      headerProps={{
        ...getHeader(overdue),
        sx: (theme) => ({
          bgcolor: color
            ? alpha(theme.palette[color].main, 0.08)
            : "action.hover",
        }),
      }}
    >
      {empty ? (
        settings.error ? (
          <Alert severity="error">{message("settingsLoadError")}</Alert>
        ) : !settingsReady ? (
          <Loading />
        ) : (
          <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
            {overdue ? (
              <Alert severity="warning">{message(emptyMessage)}</Alert>
            ) : (
              <Typography>{message(emptyMessage)}</Typography>
            )}
            {noSettings && service && (
              <CreateButton
                resource={settingsResource}
                label={message("createSetting")}
                to={`${createPath({ resource: "WebMapService", id: service.id, type: "show" })}/${settingsResource}/create`}
              />
            )}
          </Stack>
        )
      ) : (
        <>
          {settings.error ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {message("settingsLoadError")}
            </Alert>
          ) : overdue ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {message("runOverdue")}
            </Alert>
          ) : null}
          {children}
        </>
      )}
    </SimpleCard>
  );
};

export default RunHistoryCard;
