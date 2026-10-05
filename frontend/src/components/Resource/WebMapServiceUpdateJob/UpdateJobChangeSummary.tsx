import { Alert, Box, Paper, Skeleton, Stack, Typography } from "@mui/material";
import { type Identifier, useGetList, useTranslate } from "react-admin";

const categories = [
  { type: "modified", color: "info.main" },
  { type: "unchanged", color: "text.secondary" },
  { type: "added", color: "success.main" },
  { type: "removed", color: "error.main" },
] as const;

function CategoryCount({
  jobId,
  serviceId,
  type,
  color,
}: {
  jobId: Identifier;
  serviceId: Identifier;
  type: (typeof categories)[number]["type"];
  color: string;
}) {
  const translate = useTranslate();
  // Query totals across the entire job, independently of table filters and pages.
  const { total, isPending, error } = useGetList("HistoricalLayer", {
    filter: {
      history_change_reason: `updatejob_id: ${jobId}`,
      service: serviceId,
      change_type: type,
    },
    pagination: { page: 1, perPage: 1 },
    sort: { field: "historyDate", order: "DESC" },
  });
  const label = translate(`updateReview.summary.${type}`);
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderTop: 4, borderTopColor: color, minWidth: 0 }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      {error ? (
        <Alert severity="error">
          {translate("updateReview.countLoadError")}
        </Alert>
      ) : isPending ? (
        <Skeleton width={64} height={48} />
      ) : (
        <Typography
          variant="h4"
          sx={{ color, fontWeight: 600 }}
          aria-label={`${label}: ${total ?? "—"}`}
        >
          {total?.toLocaleString() ?? "—"}
        </Typography>
      )}
    </Paper>
  );
}

export default function UpdateJobChangeSummary({
  jobId,
  serviceId,
}: {
  jobId: Identifier;
  serviceId: Identifier;
}) {
  const translate = useTranslate();
  return (
    <Stack spacing={1}>
      <Box
        role="region"
        aria-label={translate("updateReview.changeSummary")}
        sx={{
          display: "grid",
          gap: 2,
          gridTemplateColumns: {
            xs: "repeat(2, minmax(0, 1fr))",
            md: "repeat(4, minmax(0, 1fr))",
          },
        }}
      >
        {categories.map((category) => (
          <CategoryCount
            key={category.type}
            jobId={jobId}
            serviceId={serviceId}
            {...category}
          />
        ))}
      </Box>
      <Typography variant="caption" color="text.secondary">
        {translate("updateReview.summaryScope")}
      </Typography>
    </Stack>
  );
}
