import type { TimelineRecord } from "./HistoryTimeline";

import { useId } from "react";
import { useTranslate } from "react-admin";

import { alpha, Box, Chip, Stack, Typography } from "@mui/material";
import { camelCase, startCase } from "lodash";

const eventColors = {
  created: "success",
  updated: "info",
  deleted: "error",
} as const;

const eventLabels = {
  created: "Created",
  updated: "Updated",
  deleted: "Deleted",
} as const;

/** A serialized GEOSGeometry arrives as GeoJSON, not as readable text. */
const isGeometryValue = (value: unknown): value is { type?: unknown } =>
  typeof value === "object" && value !== null && !Array.isArray(value) &&
  "type" in value && "coordinates" in value;

/** A serialized relationship arrives as JSON:API resource identification. */
const isRelationValue = (value: unknown): value is { id: string | number; _type?: string } =>
  typeof value === "object" && value !== null && !Array.isArray(value) &&
  "id" in value && "_type" in value;

export const formatDeltaValue = (value: unknown, translate: ReturnType<typeof useTranslate>): string => {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return translate(`ra.boolean.${value}`, { _: value ? "true" : "false" });
  if (isGeometryValue(value)) return translate("historyList.geometry", { _: "Geometry (%{type})", type: String(value.type ?? "unknown") });
  if (isRelationValue(value)) return value._type ? `${value._type} · ${value.id}` : String(value.id);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const DeltaValue = ({
  label,
  value,
  color,
}: {
  label: string;
  value: unknown;
  color: "error" | "success";
}) => {
  const translate = useTranslate();
  return (
    <Box
      sx={{
        flex: 1,
        minWidth: 0,
        p: 1.5,
        borderRadius: 1,
        borderLeft: 2,
        borderColor: `${color}.main`,
        bgcolor: (theme) => alpha(theme.palette[color].main, 0.06),
      }}
    >
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography
        component="pre"
        variant="body2"
        sx={{
          m: 0,
          mt: 0.5,
          fontFamily: "monospace",
          color: `${color}.main`,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          maxHeight: 240,
          overflowY: "auto",
        }}
      >
        {formatDeltaValue(value, translate)}
      </Typography>
    </Box>
  );
};

export interface HistoryEventDetailsProps {
  event: TimelineRecord;
  /** Resource name of the changed object, used for field labels and the fallback title. */
  related?: string;
  /** Id referenced by the control that opened these details, e.g. via aria-controls. */
  id?: string;
}

/** Previous/new values and meta data of a single historical event, shared by the compact feeds' dialogs, the timeline and the full changelog. */
const HistoryEventDetails = ({ event, related, id }: HistoryEventDetailsProps) => {
  const translate = useTranslate();
  const autoId = useId();
  const changes = event.delta ?? [];
  const fieldLabel = (field: string) => {
    if (!related) return startCase(field);
    const source = camelCase(field);
    return translate(`resources.${related}.fields.${source}`, {
      _: translate(`serviceShow.fields.${source}`, { _: startCase(field) }),
    });
  };
  const meta = [
    event.historyRelation?.id ?? "—",
    new Date(event.historyDate).toLocaleString(),
    event.historyUser
      ? translate("historyList.byUser", { _: "by %{user}", user: event.historyUser.username })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");


  return (
    <Box
      id={id ?? autoId}
      role="region"
      aria-label={translate("historyList.eventDetails", { _: "Selected event details" })}
    >
      <Stack
        direction="row"
        sx={{ alignItems: "center", gap: 1, flexWrap: "wrap" }}
      >
        <Typography sx={{ fontWeight: 600 }}>
          {event._type ?? related}
        </Typography>
        <Chip
          size="small"
          color={eventColors[event.historyType]}
          variant="outlined"
          label={
            event.actionLabel ??
            translate(`historyList.${event.historyType}`, { _: eventLabels[event.historyType] })
          }
        />
        {!!changes.length && (
          <Typography variant="caption" color="text.secondary">
            {translate("historyList.changes", { _: "%{smart_count} changes", smart_count: changes.length })}
          </Typography>
        )}
      </Stack>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mt: 1, overflowWrap: "anywhere" }}
      >
        {meta}
      </Typography>
      {changes.length ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          {changes.map((change, index) => (
            <Box key={`${change.field}:${index}`}>
              <Typography
                variant="caption"
                sx={{ display: "block", mb: 1, fontWeight: 600 }}
              >
                {fieldLabel(change.field)}
              </Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <DeltaValue
                  label={translate("historyList.previousValue", { _: "Previous value" })}
                  value={change.old}
                  color="error"
                />
                <DeltaValue
                  label={translate("historyList.newValue", { _: "New value" })}
                  value={change.new}
                  color="success"
                />
              </Stack>
            </Box>
          ))}
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          {translate("historyList.noFieldChanges", { _: "No field changes are available for this event." })}
        </Typography>
      )}
    </Box>
  );
};

export default HistoryEventDetails;

