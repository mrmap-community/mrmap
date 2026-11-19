import type { PropsWithChildren, ReactNode } from "react";
import {
  CreateButton,
  Loading,
  type RaRecord,
  useCreatePath,
  useGetList,
  useListContext,
  useRecordContext,
  useTranslate
} from "react-admin";

import {
  Alert,
  alpha,
  type CardHeaderProps,
  Stack,
  Typography,
} from "@mui/material";

import SimpleCard from "../../../../MUI/SimpleCard";

interface RunSetting extends RaRecord {
  enabled: boolean;
  runOverdue: boolean;
}

interface RunHistoryCardProps extends PropsWithChildren {
  serviceFilter: string;
  color?: "success" | "warning" | "error";
  getHeader: (
    overdue: boolean,
  ) => Pick<CardHeaderProps, "title" | "subheader" | "action">;
}

/** a configured run which is overdue: the state a warning is raised for */
const isOverdueRun = (setting: RunSetting): boolean => setting.enabled && setting.runOverdue;

/** which empty state the settings describe: nothing configured, overdue,
 *  waiting for the first run of an enabled schedule or all schedules off */
const emptyMessageKey = (
  noSettings: boolean,
  overdue: boolean,
  hasEnabledSetting: boolean,
): string => {
  if (noSettings) return "noSetting";
  if (overdue) return "runOverdue";
  return hasEnabledSetting ? "waitingForFirstRun" : "settingsDisabled";
};

/** what the card shows while there are no runs, and the notice which rides above
 *  the runs when the settings are broken or a run is overdue */
const buildNotices = ({
  settingsError,
  settingsReady,
  overdue,
  noSettings,
  emptyMessage,
  serviceId,
  settingsResource,
  createToShow,
  message,
}: {
  settingsError: unknown;
  settingsReady: boolean;
  overdue: boolean;
  noSettings: boolean;
  emptyMessage: string;
  serviceId: RaRecord["id"] | undefined;
  settingsResource: string;
  createToShow: (serviceId: RaRecord["id"]) => string;
  message: (key: string) => string;
}): { emptyNotice: ReactNode; settingsNotice: ReactNode } => {
  let emptyNotice: ReactNode;
  if (settingsError) {
    emptyNotice = <Alert severity="error">{message("settingsLoadError")}</Alert>;
  } else if (!settingsReady) {
    emptyNotice = <Loading />;
  } else {
    emptyNotice = (
      <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
        {overdue ? (
          <Alert severity="warning">{message(emptyMessage)}</Alert>
        ) : (
          <Typography>{message(emptyMessage)}</Typography>
        )}
        {noSettings && serviceId !== undefined && (
          <CreateButton
            resource={settingsResource}
            label={message("createSetting")}
            to={`${createToShow(serviceId)}/${settingsResource}/create`}
          />
        )}
      </Stack>
    );
  }

  let settingsNotice: ReactNode = null;
  if (settingsError) {
    settingsNotice = (
      <Alert severity="error" sx={{ mb: 2 }}>
        {message("settingsLoadError")}
      </Alert>
    );
  } else if (overdue) {
    settingsNotice = (
      <Alert severity="warning" sx={{ mb: 2 }}>
        {message("runOverdue")}
      </Alert>
    );
  }

  return { emptyNotice, settingsNotice };
};

const RunHistoryCard = ({
  children,
  serviceFilter,
  color: statusColor,
  getHeader,
}: RunHistoryCardProps) => {
  const { data, isPending, error, resource } = useListContext();
  const [prefix] = resource.split(/(?=Job|Run$)/);
  const settingsResource = `${prefix}Setting`;

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
  const overdue = Boolean(settingsReady && settings.data?.some(isOverdueRun));
  const color = overdue ? "warning" : statusColor;
  const hasEnabledSetting = settings.data?.some((setting) => setting.enabled) ?? false;
  const emptyMessage = emptyMessageKey(noSettings, overdue, hasEnabledSetting);

  const { emptyNotice, settingsNotice } = buildNotices({
    settingsError: settings.error,
    settingsReady,
    overdue,
    noSettings,
    emptyMessage,
    serviceId: service?.id,
    settingsResource,
    createToShow: (serviceId) =>
      createPath({ resource: "WebMapService", id: serviceId, type: "show" }),
    message,
  });

  const body: ReactNode = empty ? emptyNotice : (
    <>
      {settingsNotice}
      {children}
    </>
  );

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
      {body}
    </SimpleCard>
  );
};

export default RunHistoryCard;
