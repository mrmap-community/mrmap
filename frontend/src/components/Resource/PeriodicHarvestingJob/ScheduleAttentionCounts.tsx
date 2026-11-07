import { Link, useCreatePath, useTranslate } from "react-admin";

import ErrorIcon from "@mui/icons-material/Error";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { Button, Stack, Typography } from "@mui/material";

import useServiceAlerts from "../ServiceAlert/useServiceAlerts";

/**
 * The two states of a schedule which need an administrator, as the alerts
 * endpoint already answers them (#1082).
 *
 * `harvest_overdue` is the schedule which did not fire when its crontab said it
 * should, `harvest_schedule_too_tight` the one which promises to fire more often
 * than a run takes (#693). Both are answered by the alerts of the deployment
 * already and were shown only on the cross-service alert list, so the screen of
 * all schedules names how many of each it has and leads to them.
 *
 * A state which answers nothing is named nowhere: a zero nobody has is noise
 * above the rows, and so is the title above numbers which are all zero.
 */
const ScheduleAttentionCounts = () => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const overdue = useServiceAlerts({
    category: "harvest_overdue",
    serviceType: "CatalogueService",
  });
  const tooTight = useServiceAlerts({
    category: "harvest_schedule_too_tight",
    serviceType: "CatalogueService",
  });
  if (overdue.error || tooTight.error || overdue.isPending || tooTight.isPending) {
    return null;
  }
  const counts = [
    {
      category: "harvest_overdue",
      total: overdue.total,
      color: "error" as const,
      icon: <ErrorIcon fontSize="small" />,
    },
    {
      category: "harvest_schedule_too_tight",
      total: tooTight.total,
      color: "warning" as const,
      icon: <WarningAmberIcon fontSize="small" />,
    },
  ].filter((count) => Boolean(count.total));
  if (counts.length === 0) return null;
  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ alignItems: "center", px: 1, py: 0.5, flexWrap: "wrap" }}
    >
      <Typography variant="subtitle2">
        {translate("harvestingSchedules.attentionTitle")}
      </Typography>
      {counts.map(({ category, total, color, icon }) => {
        const categoryKey = "serviceAlerts.categories." + category;
        const label = `${translate(categoryKey)} ${total}`;
        const filter = encodeURIComponent(
          JSON.stringify({ category, serviceType: "CatalogueService" }),
        );
        const alertsList = createPath({ resource: "ServiceAlert", type: "list" });
        return (
          <Button
            key={category}
            component={Link}
            size="small"
            color={color}
            startIcon={icon}
            to={`${alertsList}?filter=${filter}`}
          >
            {label}
          </Button>
        );
      })}
    </Stack>
  );
};

export default ScheduleAttentionCounts;
