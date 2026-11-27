import type { DashboardPeriod } from "./dashboardStatistics";

import { useLocaleState, useTranslate } from "react-admin";

import RefreshIcon from "@mui/icons-material/Refresh";
import { Box, Button, MenuItem, Select, Stack, Tooltip, Typography } from "@mui/material";

import { DASHBOARD_PERIODS } from "./useDashboardPeriod";

/**
 * The header of the dashboard: what the screen answers, over which window, and
 * how current the answer is.
 *
 * The period belongs here and not to a card (#1820): the KPI row, the two time
 * series, the stacked changes and the donut all verify the same window, so the
 * screen offers one selector and every card reads the period it chooses. A
 * refresh does the same for the whole screen — a card which refreshed for
 * itself would leave the others answering an older window beside it, which is
 * exactly what the single selector exists to prevent.
 *
 * The moment of the last refresh is the moment of the click, which is the
 * honest one: the reads answered after it and the screen says nothing about
 * them beyond that.
 */
const DashboardHeader = ({ period, onPeriodChange, onRefresh, refreshedAt }: {
  period: DashboardPeriod;
  onPeriodChange: (period: DashboardPeriod) => void;
  onRefresh: () => void;
  refreshedAt: number | null;
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const moments = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium", timeStyle: "short",
  });
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      useFlexGap
      sx={{ alignItems: { xs: "flex-start", sm: "center" }, columnGap: 2, rowGap: 0.5 }}
    >
      <Box sx={{ minWidth: 0, flex: "1 1 auto" }}>
        <Typography component="h1" variant="h5">{translate("dashboard.header.title")}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0 }}>
          {translate("dashboard.header.description")}
        </Typography>
      </Box>
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 1, flexShrink: 0 }}>
        {refreshedAt !== null && <Typography variant="caption" color="text.secondary" role="status">
          {translate("dashboard.header.refreshed", { moment: moments.format(new Date(refreshedAt)) })}
        </Typography>}
        <Tooltip title={translate("dashboard.header.refresh")}>
          <span>
            <Button
              size="small" startIcon={<RefreshIcon />} onClick={onRefresh}
              aria-label={translate("dashboard.header.refresh")}
            >
              {translate("dashboard.header.refresh")}
            </Button>
          </span>
        </Tooltip>
        <Select
          size="small"
          variant="standard"
          disableUnderline
          value={period}
          onChange={event => onPeriodChange(Number(event.target.value) as DashboardPeriod)}
          inputProps={{ "aria-label": translate("dashboard.header.period") }}
          sx={{ fontSize: "0.8125rem", "& .MuiSelect-select": { py: 0.25, pr: "22px" } }}
        >
          {DASHBOARD_PERIODS.map(days => <MenuItem key={days} value={days}>
            {translate("dashboard.activity.days", { days })}
          </MenuItem>)}
        </Select>
      </Stack>
    </Stack>
  );
};

export default DashboardHeader;
