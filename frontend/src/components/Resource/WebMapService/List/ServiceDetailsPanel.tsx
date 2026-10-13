import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import VpnLockIcon from "@mui/icons-material/VpnLock";
import {
  Box,
  Chip,
  Divider,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import {
  DateField,
  EditButton,
  NumberField,
  type RaRecord,
  RecordContextProvider,
  ShowButton,
  SimpleList,
  useCreatePath,
  useListContext,
  useNotify,
  useTranslate,
} from "react-admin";
import SimpleCard from "../../../MUI/SimpleCard";
import RealtimeListBase from "../../../../jsonapi/components/Realtime/RealtimeListBase";
import { SERVICE_ALERTS } from "../../Generic/ServiceShow/ServiceAttentionTab";
import ServiceAlertChips from "../../Generic/ServiceShow/ServiceAlertChips";
import ServiceLayerCount from "./ServiceLayerCount";
import WmsViewerButtons from "../Button/ListActions";
import { formatMonitoringRun } from "../Show/Overview/MonitoringRuns/formatMonitoringRun";

/** how many updates the panel answers as the recent events of a service */
export const RECENT_EVENTS_PER_PAGE = 5;

/** the color which answers the state an update job ended in */
const statusColor = (statusCode: number) =>
  statusCode === 3 ? "error" : statusCode === 2 ? "warning" : "success";

const RecentUpdateRunsContent = () => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const { data = [], isPending } = useListContext();

  if (!isPending && data.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("serviceList.noRecentEvents")}
      </Typography>
    );
  }

  return (
    <SimpleList
      dense
      disablePadding
      sx={{
        "& .MuiListItem-root": { py: 0.5 },
        "& .MuiListItemText-root": { my: 0 },
      }}
      leftIcon={(record) => (
        <FiberManualRecordIcon
          fontSize="small"
          color={statusColor(record.statusCode)}
        />
      )}
      primaryText={(record) =>
        formatMonitoringRun(record.doneAt ?? record.dateCreated)
      }
      secondaryText={(record) => record.status}
      rowClick={(id) =>
        createPath({ resource: "WebMapServiceUpdateJob", type: "show", id })
      }
    />
  );
};

/**
 * The updates of the selected service which are running or done.
 *
 * An update of a service is answered by the update jobs of that service, which
 * are asked again when the realtime bus carries a change of them - so the panel
 * follows an update which is running without asking the api again and again.
 */
const RecentUpdateRuns = ({ service }: { service?: RaRecord }) => (
  <RealtimeListBase
    resource="WebMapServiceUpdateJob"
    filter={{ service: service?.id }}
    sort={{ field: "dateCreated", order: "DESC" }}
    perPage={RECENT_EVENTS_PER_PAGE}
    disableSyncWithLocation
  >
    <RecentUpdateRunsContent />
  </RealtimeListBase>
);

export interface ServiceDetailsPanelProps {
  /** the service the user selected in the list */
  service?: RaRecord;
}

/**
 * What an administrator needs to know about one service without leaving the list.
 *
 * The panel shows the attributes of the service which the list already answered,
 * so selecting a service asks nothing again - only the recent updates are asked
 * from the update jobs of that service.
 */
const ServiceDetailsPanel = ({ service }: ServiceDetailsPanelProps) => {
  const translate = useTranslate();
  const notify = useNotify();

  const alerts = SERVICE_ALERTS.filter((alert) =>
    Boolean(service?.[alert.flag]),
  );

  const copyIdentifier = async () => {
    if (!service?.id) {
      return;
    }
    await navigator.clipboard.writeText(String(service.id));
    notify(translate("serviceList.copiedId"), { type: "success" });
  };

  return (
    <Stack spacing={2}>
      <SimpleCard
        title={
          <Typography variant="h6" sx={{ overflowWrap: "anywhere" }}>
            {service?.title ||
              service?.stringRepresentation ||
              translate("serviceList.details")}
          </Typography>
        }
      >
        {service === undefined ? (
          <Typography variant="body2" color="text.secondary">
            {translate("serviceList.noSelection")}
          </Typography>
        ) : (
          <RecordContextProvider value={service}>
            <Stack spacing={1.5}>
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}
              >
                <Chip size="small" variant="outlined" label="WMS" />
                <ServiceAlertChips />
                {Boolean(service?.isSecured) && (
                  <Chip
                    size="small"
                    variant="outlined"
                    color="warning"
                    icon={<VpnLockIcon />}
                    label={translate("serviceList.secured")}
                  />
                )}
                {service?.isActive === false && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={translate("serviceList.inactive")}
                  />
                )}
              </Stack>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                {service?.abstract || translate("serviceList.noAbstract")}
              </Typography>
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", minWidth: 0 }}
              >
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {service?.id}
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => void copyIdentifier()}
                  aria-label={translate("serviceList.copyId")}
                >
                  <ContentCopyIcon fontSize="inherit" />
                </IconButton>
              </Stack>
              <Divider />
              <Stack
                direction="row"
                spacing={3}
                sx={{ flexWrap: "wrap", gap: 2 }}
              >
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {translate("serviceList.created")}
                  </Typography>
                  <DateField source="createdAt" showTime />
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {translate("serviceList.modified")}
                  </Typography>
                  <DateField source="lastModifiedAt" showTime />
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {translate("serviceList.hits")}
                  </Typography>
                  <NumberField source="hits" />
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {translate("serviceList.layers")}
                  </Typography>
                  <ServiceLayerCount serviceId={service?.id} />
                </Box>
              </Stack>
              {alerts.map((alert) => (
                <Stack
                  key={alert.flag}
                  direction="row"
                  spacing={1}
                  sx={{ alignItems: "center", flexWrap: "wrap" }}
                >
                  <Chip
                    size="small"
                    color={alert.severity}
                    label={translate(
                      `serviceAttention.shortLabels.${alert.flag}`,
                    )}
                  />
                  <Typography variant="caption" color="text.secondary">
                    {translate(`serviceAttention.alerts.${alert.flag}`)}
                  </Typography>
                  {alert.at && Boolean(service?.[alert.at]) && (
                    <Stack
                      direction="row"
                      spacing={0.5}
                      sx={{ alignItems: "center" }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        {translate("serviceAttention.at")}
                      </Typography>
                      <DateField source={alert.at} showTime />
                    </Stack>
                  )}
                </Stack>
              ))}
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}
              >
                <ShowButton />
                <EditButton />
                <WmsViewerButtons />
              </Stack>
            </Stack>
          </RecordContextProvider>
        )}
      </SimpleCard>
      {service !== undefined && (
        <SimpleCard title={translate("serviceList.recentEvents")}>
          <RecentUpdateRuns service={service} />
        </SimpleCard>
      )}
    </Stack>
  );
};

export default ServiceDetailsPanel;
