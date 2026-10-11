import { alpha, Alert, Chip, Stack, Typography } from "@mui/material";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import type { PropsWithChildren } from "react";
import {
  Button,
  Loading,
  SimpleList,
  useListContext,
  useRecordContext,
  useTranslate,
} from "react-admin";
import { Link } from "react-router-dom";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";

import RunHarvestingButton from "./RunHarvestingButton";

const HarvestingSchedulesCardBase = ({ children }: PropsWithChildren) => {
  const { data, total, isPending, error } = useListContext();
  const service = useRecordContext();
  const translate = useTranslate();
  const message = (key: string) => translate(`harvestingSchedules.${key}`);
  const enabled = data?.some((schedule) => schedule.enabled);
  const hasSchedules = (data?.length ?? 0) > 0;
  const color = hasSchedules ? (enabled ? "success" : "warning") : undefined;
  const path = `/CatalogueService/${service?.id}/show/PeriodicHarvestingJob`;
  return (
    <SimpleCard
      divider={false}
      cardProps={{
        variant: "outlined",
        sx: {
          width: "100%",
          minWidth: 0,
          flex: 1,
          borderColor: color ? `${color}.main` : "divider",
        },
      }}
      headerProps={{
        title: translate("serviceShow.schedules"),
        subheader: hasSchedules
          ? translate("harvestingSchedules.count", {
              smart_count: total,
            })
          : undefined,
        action: (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <RunHarvestingButton serviceId={service?.id} />
            {hasSchedules && (
              <Chip
                size="small"
                color={color}
                variant="outlined"
                label={message(enabled ? "enabled" : "disabled")}
              />
            )}
          </Stack>
        ),
        sx: (theme) => ({
          bgcolor: color
            ? alpha(theme.palette[color].main, 0.08)
            : "action.hover",
        }),
      }}
      footer={
        service && (
          <Button component={Link} to={path} label="serviceShow.configure" />
        )
      }
    >
      {isPending ? (
        <Loading />
      ) : error ? (
        <Alert severity="error">{message("loadError")}</Alert>
      ) : hasSchedules ? (
        children
      ) : (
        <Stack spacing={2} sx={{ alignItems: "flex-start" }}>
          <Typography>{message("empty")}</Typography>
          {service && (
            <Button
              component={Link}
              to={`${path}/create`}
              label="harvestingSchedules.create"
            />
          )}
        </Stack>
      )}
      {hasSchedules && !enabled && !error && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {message("disabledMessage")}
        </Typography>
      )}
    </SimpleCard>
  );
};

const HarvestingSchedulesList = () => {
  const translate = useTranslate();
  return (
    <SimpleList
      dense
      disablePadding
      rowClick={false}
      sx={{
        "& .MuiListItem-root": { py: 0.5 },
        "& .MuiListItemText-root": { my: 0 },
      }}
      leftIcon={(record) => (
        <FiberManualRecordIcon
          color={record.enabled ? "success" : "disabled"}
        />
      )}
      primaryText={(record) => record.scheduling}
      secondaryText={(record) =>
        record.enabled
          ? translate("harvestingSchedules.nextRun", {
              time: record.timeUntilNextRun,
            })
          : translate("harvestingSchedules.disabled")
      }
    />
  );
};

const HarvestingSchedulesCard = () => {
  const service = useRecordContext();
  const operation = useOperation(
    "list_related_PeriodicHarvestingJob_of_CatalogueService",
  );
  if (!service || !operation) return null;
  return (
    <ListGuesser
      resource="PeriodicHarvestingJob"
      relatedResource={{ resource: "CatalogueService", id: service.id }}
      disableSyncWithLocation
      sort={{ field: "id", order: "DESC" }}
      perPage={5}
      actions={false}
      filters={undefined}
      aside={undefined}
      pagination={false}
      empty={false}
      component={HarvestingSchedulesCardBase}
      storeKey={`CatalogueService.${service.id}.PeriodicHarvestingJob.overview`}
      refetchInterval={30000}
      defaultSelectedColumns={["enabled", "scheduling", "timeUntilNextRun"]}
      dataGridProps={{ component: HarvestingSchedulesList }}
    />
  );
};

export { HarvestingSchedulesCardBase };
export default HarvestingSchedulesCard;
