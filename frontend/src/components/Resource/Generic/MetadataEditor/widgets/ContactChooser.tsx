import type { CreateCapableWidgetProps } from "./types";

import { useCallback, type ReactElement, type HTMLAttributes } from "react";
import { type RaRecord, useTranslate } from "react-admin";

import { Box, Chip, Stack } from "@mui/material";

import SchemaAutocompleteInput from "../../../../../jsonapi/components/SchemaAutocompleteInput";
import useSchemaRecordRepresentation from "../../../../../jsonapi/hooks/useSchemaRecordRepresentation";

/**
 * Contact chooser for one contact slot of a metadata record (#1246).
 *
 * It is the schema layer's `SchemaAutocompleteInput` for the existing
 * `MetadataContact` resource — searchable, with the type-to-create dialog the
 * schema hands to-one relationships — plus one thing the plain chooser lacks:
 * each option shows how often the contact is already in use, so the curator
 * can pick a reusable entry instead of creating a near-duplicate. The count
 * rides as `usage_count` on the contact list endpoint (added with #1246) and
 * is asked for via sparse fields; options that came from the record's include
 * rather than from the list endpoint carry no count and show no chip.
 *
 * The role of the contact is the slot itself: `metadataContact`,
 * `datasetContact` and `applicationContact` are the writable fields, and the
 * write maps each to its fixed `CI_RoleCode` — a free role select would not
 * round-trip.
 */
const ContactChooser = ({
  source,
  reference = "MetadataContact",
  label,
  helperText,
  required,
  disabled,
  validate,
  create,
  createLabel,
  // the to-one contact has no array default to hand on; the single input
  // starts empty
  defaultValue: _defaultValue,
  ...rest
}: CreateCapableWidgetProps): ReactElement => {
  const translate = useTranslate();
  const representation = useSchemaRecordRepresentation({ resource: reference });

  // the input text stays the plain representation; only the dropdown rows
  // gain the reuse chip, so the filled input never holds a stacked layout
  const renderOption = useCallback(
    (props: HTMLAttributes<HTMLLIElement>, option: RaRecord) => (
      <li {...props}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: "center", width: "100%", minWidth: 0 }}
        >
          <Box sx={{ flexGrow: 1, minWidth: 0, overflowWrap: "anywhere" }}>
            {representation(option)}
          </Box>
          {typeof option.usageCount === "number" && (
            <Chip
              size="small"
              variant="outlined"
              label={translate("metadataEditor.contacts.reused", {
                smart_count: option.usageCount,
              })}
            />
          )}
        </Stack>
      </li>
    ),
    [representation, translate],
  );

  return (
    <SchemaAutocompleteInput
      {...rest}
      source={source}
      reference={reference}
      label={label}
      helperText={helperText}
      isRequired={required}
      disabled={disabled}
      validate={validate}
      create={create}
      createLabel={createLabel}
      renderOption={renderOption}
      params={{
        meta: {
          jsonApiParams: {
            [`fields[${reference}]`]: "id,string_representation,usage_count",
          },
        },
      }}
    />
  );
};

export default ContactChooser;
