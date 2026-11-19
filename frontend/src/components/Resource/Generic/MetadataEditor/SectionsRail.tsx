/**
 * The left rail of the record editor (#1245).
 *
 * The mockups show the ISO sections of the profile as a vertical rail whose
 * badge states how many findings each section currently holds; the read-only
 * areas below it reuse the `RecordShow` cards rather than a second overview.
 * Nothing here knows the record kind: the editor hands it what the profile
 * answered, so a different profile only moves the labels and counts.
 */

import { type ReactElement } from "react";
import { useTranslate } from "react-admin";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import {
  Box,
  Chip,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";

export interface RailItem {
  id: string;
  label: string;
}

export interface RailCounts {
  errors: number;
  warnings: number;
}

interface SectionsRailProps {
  sections: RailItem[];
  /** the read-only areas below the profile sections */
  readOnly: RailItem[];
  active: string;
  onSelect: (id: string) => void;
  /** findings per section id, for the badge */
  counts: Record<string, RailCounts>;
  /** the profile's own mandatory check against the current values */
  completeness?: { filled: number; total: number };
}

const SectionBadge = ({ counts }: { counts?: RailCounts }) => {
  if (counts && counts.errors > 0)
    return (
      <Chip
        size="small"
        color="error"
        label={counts.errors}
        sx={{ minWidth: 20 }}
      />
    );
  if (counts && counts.warnings > 0)
    return (
      <Chip
        size="small"
        color="warning"
        label={counts.warnings}
        sx={{ minWidth: 20 }}
      />
    );
  return <CheckCircleIcon color="success" fontSize="small" />;
};

const SectionsRail = ({
  sections,
  readOnly,
  active,
  onSelect,
  counts,
  completeness,
}: SectionsRailProps): ReactElement => {
  const translate = useTranslate();
  return (
    <Box sx={{ width: 240, flexShrink: 0 }}>
      <Typography variant="overline" color="text.secondary">
        {translate("metadataEditor.sections")}
      </Typography>
      <List disablePadding>
        {sections.map((section) => (
          <ListItemButton
            key={section.id}
            selected={active === section.id}
            onClick={() => onSelect(section.id)}
            sx={{ borderRadius: 1 }}
          >
            <ListItemText primary={section.label} />
            <SectionBadge counts={counts[section.id]} />
          </ListItemButton>
        ))}
      </List>
      {completeness && completeness.total > 0 && (
        <Stack spacing={0.5} sx={{ p: 1 }}>
          <Typography variant="body2">
            {translate("metadataEditor.completeness")}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={Math.round(
              (completeness.filled / completeness.total) * 100,
            )}
          />
          <Typography variant="caption" color="text.secondary">
            {translate("metadataEditor.completenessCount", {
              filled: completeness.filled,
              total: completeness.total,
            })}
          </Typography>
        </Stack>
      )}
      <List disablePadding>
        {readOnly.map((item) => (
          <ListItemButton
            key={item.id}
            selected={active === item.id}
            onClick={() => onSelect(item.id)}
            sx={{ borderRadius: 1 }}
          >
            <ListItemIcon sx={{ minWidth: 28 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  border: 1,
                  borderColor: "text.disabled",
                }}
              />
            </ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );
};

export default SectionsRail;
