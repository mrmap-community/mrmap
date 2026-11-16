import type { MetadataWidgetProps } from "./types";

import { useMemo, type ReactElement } from "react";
import {
  ArrayInput,
  SimpleFormIterator,
  type RaRecord,
  useTranslate,
} from "react-admin";
import { useWatch } from "react-hook-form";

import { Box, Typography } from "@mui/material";

import SchemaAutocompleteInput from "../../../../../jsonapi/components/SchemaAutocompleteInput";
import CreateSuggestionDialog from "../../../../Dialog/CreateSuggestionDialog";

// the text the write-back puts into gco:CharacterString for one row; rows
// arrive as plain { id } references until the include or a getMany resolved
// them, so fall back to the id instead of guessing a text
const keywordText = (value: RaRecord): string =>
  (typeof value?.stringRepresentation === "string" &&
    value.stringRepresentation) ||
  (typeof value?.keyword === "string" && value.keyword) ||
  `#${value?.id ?? "?"}`;

/**
 * Keyword picker for one to-many keyword field (#1246).
 *
 * Reuses the pieces the schema layer already ships for relationship inputs:
 * `ArrayInput` + `SimpleFormIterator` give the per-element add, delete and
 * drag-reorder the profile editors are expected to have; each row is a
 * `SchemaAutocompleteInput` in row mode (no `source` — it binds to the whole
 * row value) so the searchable picker, the include resolution and the
 * `CreateSuggestionDialog` type-to-create work per row the way they do for
 * the single-value inputs. Typing a new keyword creates a `Keyword` record;
 * the write then emits it as a plain `gco:CharacterString`, which the preview
 * below shows. (Thesaurus grouping and the `gmx:Anchor` form wait on the
 * thesaurus source question of #1246.)
 */
const KeywordsInput = ({
  source,
  reference = "Keyword",
  label,
  helperText,
  required,
  disabled,
  validate,
  defaultValue,
}: MetadataWidgetProps): ReactElement => {
  const translate = useTranslate();
  const values = useWatch({ name: source }) as RaRecord[] | undefined;

  const preview = useMemo(() => {
    const rows = Array.isArray(values) ? values : [];
    if (rows.length === 0) return undefined;
    return [
      "<gmd:keywords><gmd:MD_Keywords>",
      ...rows.map(
        (row) =>
          `  <gmd:keyword><gco:CharacterString>${keywordText(row)}</gco:CharacterString></gmd:keyword>`,
      ),
      "</gmd:MD_Keywords></gmd:keywords>",
    ].join("\n");
  }, [values]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <ArrayInput
        source={source}
        label={label}
        helperText={helperText}
        required={required}
        validate={validate}
        defaultValue={defaultValue}
      >
        <SimpleFormIterator>
          <SchemaAutocompleteInput
            reference={reference}
            disabled={disabled}
            create={<CreateSuggestionDialog guesserProps={{ resource: reference }} />}
            createLabel={translate("metadataEditor.keywords.createHint")}
          />
        </SimpleFormIterator>
      </ArrayInput>
      {preview !== undefined && (
        <Box>
          <Typography variant="caption" color="text.secondary">
            {translate("metadataEditor.keywords.preview")}
          </Typography>
          <Typography
            component="pre"
            variant="caption"
            sx={{ fontFamily: "monospace", whiteSpace: "pre-wrap", m: 0 }}
          >
            {preview}
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default KeywordsInput;
