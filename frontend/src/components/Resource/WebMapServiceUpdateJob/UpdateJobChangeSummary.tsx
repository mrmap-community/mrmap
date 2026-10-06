import {
  Box,
  Chip,
  Paper,
  Skeleton,
  Stack,
  Typography
} from "@mui/material";
import { useRecordContext, useTranslate } from "react-admin";

const categories = [
  { type: "changedLayers", color: "info.main" },
  { type: "unchangedLayers", color: "text.secondary" },
  { type: "addedLayers", color: "success.main" },
  { type: "deletedLayers", color: "error.main" },
] as const;

const CategoryCount = ({
  type,
  color,
  compact = false,
}: {
  type: (typeof categories)[number]["type"];
  color: string;
  compact?: boolean;
}) => {
  const translate = useTranslate();
  // Query totals across the entire job, independently of table filters and pages.
  const record = useRecordContext()
  const total = record?.[type] || 0

  const label = translate(`updateReview.summary.${type}`);
  if (compact) {
    return record === undefined ? (
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
      {record === undefined ? (
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
  compact = false,
}: {
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
          .filter((category) => category.type !== "unchangedLayers")
          .map((category) => (
            <CategoryCount
              key={category.type}
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
