import {
  Alert,
  Box,
  Chip,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from "@mui/material";
import { type Identifier, useGetList, useTranslate } from "react-admin";

const categories = [
  { type: "modified", color: "info.main" },
  { type: "unchanged", color: "text.secondary" },
  { type: "added", color: "success.main" },
  { type: "removed", color: "error.main" },
] as const;

const CategoryCount = ({
  jobId,
  serviceId,
  type,
  color,
  compact = false,
}: {
  jobId: Identifier;
  serviceId: Identifier;
  type: (typeof categories)[number]["type"];
  color: string;
  compact?: boolean;
}) => {
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
  if (compact) {
    return error ? (
      <Typography component="span" variant="caption" color="error">
        {translate("updateReview.countLoadError")}
      </Typography>
    ) : isPending ? (
      <Skeleton width={80} sx={{ display: "inline-block" }} />
    ) : (
      <Chip
        component="span"
        size="small"
        variant="outlined"
        sx={{ color, height: 20, "& .MuiChip-label": { px: 0.75 } }}
        label={`${label}: ${total?.toLocaleString() ?? "—"}`}
        aria-label={`${label}: ${total ?? "—"}`}
      />
    );
  }
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
};

const UpdateJobChangeSummary = ({
  jobId,
  serviceId,
  compact = false,
}: {
  jobId: Identifier;
  serviceId: Identifier;
  compact?: boolean;
}) => {
  const translate = useTranslate();
  if (compact) {
    return (
      <Box
        component="span"
        role="region"
        aria-label={translate("updateReview.changeSummary")}
        sx={{ display: "inline-flex", gap: 0.5, flexWrap: "wrap" }}
      >
        {categories
          .filter((category) => category.type !== "unchanged")
          .map((category) => (
            <CategoryCount
              key={category.type}
              jobId={jobId}
              serviceId={serviceId}
              compact
              {...category}
            />
          ))}
      </Box>
    );
  }
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
};

export default UpdateJobChangeSummary;
