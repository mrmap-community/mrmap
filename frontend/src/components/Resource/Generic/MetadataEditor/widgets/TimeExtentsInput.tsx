import type { MetadataWidgetProps } from "./types";

import { useMemo, useState, type ReactElement } from "react";
import {
  type RaRecord,
  useCreate,
  useGetMany,
  useNotify,
  useTranslate,
} from "react-admin";
import { useFormContext, useWatch } from "react-hook-form";

import { Box, Button, IconButton, Stack, TextField, Typography } from "@mui/material";

import { IncludedRecordFields } from "../../RecordShow/RecordFields";

// datetime-local yields "YYYY-MM-DDTHH:mm" (with ":ss" only when a step
// asks); the ISO instant is completed explicitly so the naive wall-clock
// entry is sent as the UTC time it was meant to be
const toInstant = (value: string): string =>
  `${value.length === 16 ? `${value}:00` : value}Z`;

/**
 * Temporal extent editor for the `timeExtents` relation (#1246).
 *
 * `TimeExtent` rows are shared lookups — the API offers list, retrieve and
 * create, not edit — so this widget is deliberately not a row editor: the
 * attached extents are listed (resolved through the record's include, with a
 * `getMany` fallback the same way `SchemaAutocompleteInput` resolves its
 * rows), removing detaches the row from the record without touching it, and
 * adding creates a new row from a small begin/end form with inline
 * validation. An open extent is allowed on both sides; only begin after end
 * is refused, mirroring the serializer's own check.
 */
const TimeExtentsInput = ({
  source,
  label,
  helperText,
  required,
  disabled,
}: MetadataWidgetProps): ReactElement => {
  const translate = useTranslate();
  const notify = useNotify();
  const { setValue } = useFormContext();

  const values = useWatch({ name: source }) as RaRecord[] | undefined;
  const rows = useMemo(() => (Array.isArray(values) ? values : []), [values]);
  // rows the include already delivered carry their positions; only the rest
  // needs a lookup
  const missing = useMemo(
    () =>
      rows.filter(
        (row) => row?.id != null && row.beginPosition == null && row.endPosition == null,
      ),
    [rows],
  );
  const { data: fetched } = useGetMany(
    "TimeExtent",
    { ids: missing.map((row) => row.id) },
    { enabled: missing.length > 0 },
  );

  const [begin, setBegin] = useState("");
  const [end, setEnd] = useState("");
  const orderError = begin !== "" && end !== "" && begin > end;

  const [createExtent, { isPending: creating }] = useCreate();

  const addExtent = () => {
    if (orderError || disabled || (begin === "" && end === "")) return;
    const data: Record<string, string> = {};
    if (begin !== "") data.beginPosition = toInstant(begin);
    if (end !== "") data.endPosition = toInstant(end);
    createExtent(
      "TimeExtent",
      { data },
      {
        onSuccess: (created) => {
          setValue(
            source,
            [...rows, { id: created.data.id }],
            { shouldDirty: true },
          );
          setBegin("");
          setEnd("");
          notify("metadataEditor.timeExtents.added", { type: "success" });
        },
        onError: () => notify("metadataEditor.timeExtents.addFailed", { type: "error" }),
      },
    );
  };

  const removeExtent = (id: string | number) =>
    setValue(
      source,
      rows.filter((row) => row.id !== id).map((row) => ({ id: row.id })),
      { shouldDirty: true },
    );

  return (
    <Box>
      <Typography variant="subtitle1" component="label">
        {label}
        {required ? " *" : ""}
      </Typography>
      {helperText != null && (
        <Typography variant="caption" color="text.secondary" component="div">
          {helperText}
        </Typography>
      )}
      <Stack spacing={0.5} sx={{ mt: 1 }}>
        {rows.map((row) => (
          <Stack
            key={String(row.id)}
            direction="row"
            sx={{ alignItems: "center" }}
          >
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <IncludedRecordFields
                resource="TimeExtent"
                record={
                  fetched?.find((record) => record.id === row.id) ?? row
                }
                sources={["beginPosition", "endPosition"]}
              />
            </Box>
            {!disabled && (
              <IconButton
                size="small"
                aria-label={translate("metadataEditor.timeExtents.remove")}
                onClick={() => removeExtent(row.id)}
              >
                <Typography variant="body2">✕</Typography>
              </IconButton>
            )}
          </Stack>
        ))}
        {rows.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            {translate("metadataEditor.timeExtents.none")}
          </Typography>
        )}
      </Stack>
      {!disabled && (
        <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", mt: 1 }}>
          <TextField
            label={translate("metadataEditor.timeExtents.begin")}
            type="datetime-local"
            size="small"
            value={begin}
            onChange={(event) => setBegin(event.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            label={translate("metadataEditor.timeExtents.end")}
            type="datetime-local"
            size="small"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            error={orderError}
            helperText={
              orderError
                ? translate("metadataEditor.timeExtents.orderError")
                : translate("metadataEditor.timeExtents.hintUtc")
            }
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={orderError || creating || (begin === "" && end === "")}
            onClick={addExtent}
          >
            {translate("metadataEditor.timeExtents.add")}
          </Button>
        </Stack>
      )}
    </Box>
  );
};

export default TimeExtentsInput;
