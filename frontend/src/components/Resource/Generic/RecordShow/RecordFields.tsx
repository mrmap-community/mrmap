import { Box, Chip, Stack, Typography } from "@mui/material";
import { createElement } from "react";
import {
  Labeled,
  ReferenceField,
  TextField,
  RecordContextProvider,
  SimpleShowLayout,
  useRecordContext,
  useResourceContext,
  useTranslate,
  type RaRecord,
} from "react-admin";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";

export const choiceLabel = (
  value: unknown,
  choices?: { id: unknown; name: string }[],
) => choices?.find((choice) => String(choice.id) === String(value))?.name;

const IncludedValues = ({
  resource,
  values,
}: {
  resource: string;
  values: RaRecord[];
}) => {
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: `retrieve_${resource}`,
    forInput: false,
  });
  const choices = fields.find((field) => field.props.source === "value")?.props
    .choices;
  return (
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
      {values.map((value) => (
        <Chip
          key={value.id}
          size="small"
          label={
            choiceLabel(value.value ?? value.id, choices) ??
            value.stringRepresentation ??
            translate("recordShow.unknown")
          }
        />
      ))}
    </Stack>
  );
};

// Presentation selects fields; types, labels and enum choices remain schema-owned.
const RecordFields = ({
  sources,
  resource: resourceProp,
}: {
  sources: string[];
  resource?: string;
}) => {
  const resource = useResourceContext({ resource: resourceProp });
  const record = useRecordContext();
  const translate = useTranslate();
  const fields = useFieldsForOperation({
    operationId: `retrieve_${resource}`,
    forInput: false,
    ignoreId: false,
  });
  return (
    <SimpleShowLayout sx={{ p: 0, overflowWrap: "anywhere" }}>
      {sources.map((source) => {
        const field = fields.find(
          (candidate) => candidate.props.source === source,
        );
        if (!field) return null;
        const value = record?.[source];
        if (Array.isArray(value) && field.props.reference)
          return (
            <Labeled key={source} label={field.props.label}>
              {value.length ? (
                <IncludedValues
                  resource={field.props.reference}
                  values={value}
                />
              ) : (
                <Typography>—</Typography>
              )}
            </Labeled>
          );
        if ((source === "createdBy" || source === "lastModifiedBy") && value)
          return (
            <Labeled key={source} label={field.props.label}>
              <ReferenceField
                source={`${source}.id`}
                reference="User"
                link={(user) =>
                  `/User?filter=${encodeURIComponent(JSON.stringify({ id: user.id }))}`
                }
              >
                <TextField source="username" />
              </ReferenceField>
            </Labeled>
          );
        if (
          source === "abstract" ||
          source === "lineageStatement" ||
          source === "insufficientQuality"
        )
          return (
            <Labeled key={source} label={field.props.label}>
              <Typography sx={{ whiteSpace: "pre-wrap" }}>
                {value || "—"}
              </Typography>
            </Labeled>
          );
        if (field.props.choices)
          return (
            <Labeled key={source} label={field.props.label}>
              <Typography>
                {value == null
                  ? "—"
                  : (choiceLabel(value, field.props.choices) ??
                    translate("recordShow.unknown"))}
              </Typography>
            </Labeled>
          );
        return createElement(
          source === "resolution" ? TextField : field.component,
          { ...field.props, key: source, emptyText: "—" },
        );
      })}
    </SimpleShowLayout>
  );
};

export const IncludedRecordFields = ({
  resource,
  record,
  sources,
}: {
  resource: string;
  record?: RaRecord;
  sources: string[];
}) =>
  record ? (
    <RecordContextProvider value={record}>
      <Box>
        <RecordFields resource={resource} sources={sources} />
      </Box>
    </RecordContextProvider>
  ) : (
    <Typography>—</Typography>
  );

export default RecordFields;
