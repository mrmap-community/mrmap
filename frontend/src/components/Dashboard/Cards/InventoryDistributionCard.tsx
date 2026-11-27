import { useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import DonutLargeIcon from "@mui/icons-material/DonutLarge";
import { Box, Button, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { PieChart } from "@mui/x-charts/PieChart";

import SimpleCard from "../../MUI/SimpleCard";
import { dashboardResourceColor } from "../dashboardColors";
import {
  dashboardDistribution,
  type InventoryCountSource,
  type InventoryDistribution,
} from "../dashboardInventory";

/** the height of the donut itself; the card stays within the middle row of the mockup */
const PLOT_HEIGHT = 132;

/** the share a resource must reach to keep its own arc; smaller ones answer `Other` */
const OTHER_THRESHOLD = 5;

/** the color of the arc which groups the small shares, which belongs to no resource */
const OTHER = "Other";

/**
 * The distribution of the registered resources of the deployment.
 *
 * The donut answers an inventory and not a history, and not the distribution of
 * the background work either: every arc is the count one kind of resource
 * carries today, so the circle is the inventory the caller is allowed to see and
 * never the distinct objects behind it. The denominator is said beside it and is
 * the sum of the counts which were answered — a resource whose count is missing
 * is named instead of silently enlarging the shares of the others.
 *
 * Small shares are grouped into one arc, because thirteen unreadable slivers
 * answer nothing; the exact counts and percentages stay in the list beside the
 * circle, which is the accessible form of the same answer and never depends on
 * the grouping.
 */
const InventoryDistributionCard = ({ sources }: {
  /** the registered counts of the inventory kinds the caller may read */
  sources: InventoryCountSource[];
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [grouped, setGrouped] = useState(true);
  const distribution: InventoryDistribution = dashboardDistribution(sources);
  const numbers = new Intl.NumberFormat(locale);
  const percent = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  const resourceName = (resource: string) => resource === OTHER
    ? translate("dashboard.distribution.other")
    : translate(`dashboard.activity.resourceNames.${resource}`, {
      _: translate(`resources.${resource}.plural`, { _: resource }),
    });

  const body = () => {
    if (distribution.status !== "ready") {
      const messages = {
        loading: "historyChart.asking", error: "historyChart.error",
        partial: "historyChart.partial", unsupported: "historyChart.noStatistics",
      } as const;
      return <Typography variant="body2" role="status" sx={{ py: 1 }}>
        {translate(messages[distribution.status])}
      </Typography>;
    }
    const { slices, total, unavailable } = distribution;
    const small = slices.filter(slice => slice.percent < OTHER_THRESHOLD);
    const shown = grouped && small.length > 1
      ? [
        ...slices.filter(slice => slice.percent >= OTHER_THRESHOLD),
        {
          resource: OTHER,
          count: small.reduce((sum, slice) => sum + slice.count, 0),
          percent: small.reduce((sum, slice) => sum + slice.percent, 0),
        },
      ]
      : slices;
    return <Box>
      {total === 0 && <Typography variant="caption" role="status" sx={{ display: "block" }}>
        {translate("dashboard.distribution.empty")}
      </Typography>}
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 1 }}>
        <Box sx={{ minWidth: 0, flex: "0 1 55%" }}>
          <PieChart
            aria-label={translate("dashboard.distribution.title")}
            height={PLOT_HEIGHT}
            margin={{ left: 0, right: 0, top: 4, bottom: 4 }}
            series={[{
              id: "inventory",
              data: shown.map(slice => ({
                id: slice.resource,
                value: slice.count,
                label: resourceName(slice.resource),
                color: slice.resource === OTHER
                  ? theme.palette.grey[500]
                  : dashboardResourceColor(theme, slice.resource),
              })),
              innerRadius: "55%",
              outerRadius: "95%",
              cornerRadius: 2,
              paddingAngle: 1,
              valueFormatter: (value: { value: number | null }) => numbers.format(value.value ?? 0),
            }]}
            skipAnimation
          />
        </Box>
        <Box component="ul" sx={{ flex: "1 1 45%", m: 0, p: 0, listStyle: "none", minWidth: 0 }}>
          {slices.map(slice => <Typography
            component="li" variant="caption" key={slice.resource} sx={{ display: "block", minWidth: 0 }}
          >
            <Box
              component="span" sx={{
                display: "inline-block", width: 8, height: 8, mr: 0.5, borderRadius: "2px",
                bgcolor: slice.resource === OTHER
                  ? "grey.500" : dashboardResourceColor(theme, slice.resource),
              }}
            />
            {resourceName(slice.resource)}:{" "}
            <strong>{numbers.format(slice.count)}</strong>{" · "}
            {percent.format(slice.percent)}%
          </Typography>)}
        </Box>
      </Stack>
      {unavailable.length > 0 && <Typography variant="caption" color="warning.main" role="status">
        {translate("dashboard.distribution.unavailable", {
          resources: unavailable.map(gap => resourceName(gap.resource)).join(", "),
        })}
      </Typography>}
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", justifyContent: "space-between", columnGap: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {translate("dashboard.distribution.denominator", {
            total: numbers.format(total),
            resources: numbers.format(slices.length),
            smart_count: slices.length,
          })}
        </Typography>
        {small.length > 1 && <Button
          size="small" onClick={() => setGrouped(without => !without)}
          sx={{ fontSize: "0.75rem" }}
        >
          {translate(grouped ? "dashboard.distribution.explain" : "dashboard.distribution.group", {
            resources: small.length,
            threshold: OTHER_THRESHOLD,
          })}
        </Button>}
      </Stack>
    </Box>;
  };

  return (
    <SimpleCard
      title={<Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.25, minWidth: 0 }}>
        <DonutLargeIcon fontSize="small" color="primary" />
        <Typography component="h2" variant="subtitle2" sx={{ minWidth: 0 }} noWrap>
          {translate("dashboard.distribution.title")}
        </Typography>
      </Stack>}
      subheader={<Typography variant="caption" color="text.secondary">
        {translate("dashboard.distribution.scope")}
      </Typography>}
      headerProps={{ sx: { alignItems: "flex-start", minHeight: 40, px: 1.5, py: 0.25 } }}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2, height: "100%" } }}
      contentProps={{ sx: { px: 1, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } } }}
      divider={false}
    >
      {body()}
    </SimpleCard>
  );
};

export default InventoryDistributionCard;
