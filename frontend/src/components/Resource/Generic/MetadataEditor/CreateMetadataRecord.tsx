import type { FieldDefinition } from "../../../../jsonapi/utils";

import { useMemo } from "react";
import {
  Create,
  SaveButton,
  SimpleForm,
  TextInput,
  Toolbar,
  useGetList,
  useResourceContext,
  useTranslate,
} from "react-admin";
import { useWatch } from "react-hook-form";

import { Alert, Box, Chip, FormControlLabel, Radio, Stack, Typography } from "@mui/material";

import GlobalFormError from "../../../../jsonapi/components/GlobalFormError";
import SchemaFormFields from "../../../../jsonapi/components/SchemaFormFields";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import { parseProfileSections, planCreate, type CreatePlan } from "./createPlan";

// the toolbar of a created record must not offer the undo of react-admin:
// the row and its document are written together by the backend (#1241)
const CreateMetadataToolbar = () => (
  <Toolbar>
    <SaveButton alwaysEnable />
  </Toolbar>
);

/**
 * The "what you get" panel: it names what the POST will answer — the sections
 * that start with content, the ones Advanced mode (#1245) fills later, the
 * generated-or-chosen identifier and the marker the record gets — instead of
 * letting the creator guess. The plan is derived from the profile the form
 * currently holds, so choosing another profile restates the promise.
 */
const CreatePlanPanel = ({ plan, profileChosen }: { plan: CreatePlan; profileChosen: boolean }) => {
  const translate = useTranslate();
  return (
    <SimpleCard title={translate("recordCreate.getTitle")}>
      <Stack spacing={1}>
        {!profileChosen && (
          <Typography variant="body2">{translate("recordCreate.profileHint")}</Typography>
        )}
        {profileChosen && (
          <>
            <Box>
              <Typography variant="body2">{translate("recordCreate.getCreated")}</Typography>
              <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
                {plan.createdSections.map(section => (
                  <Chip key={section.id} size="small" label={section.label} />
                ))}
              </Stack>
            </Box>
            {plan.laterSections.length > 0 && (
              <Box>
                <Typography variant="body2">{translate("recordCreate.getAddedLater")}</Typography>
                <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
                  {plan.laterSections.map(section => (
                    <Chip key={section.id} size="small" variant="outlined" label={section.label} />
                  ))}
                </Stack>
              </Box>
            )}
          </>
        )}
        <Typography variant="body2">{translate("recordCreate.getIdentity")}</Typography>
        <Typography variant="body2">{translate("recordCreate.getMarked")}</Typography>
      </Stack>
    </SimpleCard>
  );
};

/**
 * Inside `<SimpleForm>`: reads the watched profile relationship from the
 * form's own react-hook-form context — as a child of the form it can both
 * ask which fields the schema renders and restate the plan when the profile
 * changes.
 */
const WizardBody = ({ profiles, operationId }: {
  profiles: { id?: unknown; sections?: unknown }[];
  operationId: string;
}) => {
  const translate = useTranslate();
  const definitions = useFieldsForOperation({ operationId });
  const offered = useMemo(
    () => definitions.filter(definition => !definition.props.disabled).map(definition => definition.props.source),
    [definitions],
  );
  const values = useWatch();
  const selected = values?.profile;
  const sectionsByProfile = useMemo(() => {
    const map = new Map<string, ReturnType<typeof parseProfileSections>>();
    profiles.forEach(profile => map.set(String(profile.id), parseProfileSections(profile.sections)));
    return map;
  }, [profiles]);
  // the relationship input answers `{ id }`; tolerate the bare id as well
  const selectedId = typeof selected === "string" ? selected : selected?.id;
  const sections = sectionsByProfile.get(String(selectedId)) ?? [];

  const plan = planCreate({ sections, offered });
  // the wizard enforces the profile's mandatory flag on fields the schema
  // leaves optional, and the profile itself must be chosen by a person
  const overrides: FieldDefinition[] = definitions
    .filter(definition => definition.props.source === "profile" || plan.askedFields.includes(definition.props.source))
    .map(definition => ({
      component: definition.component,
      props: { ...definition.props, required: true },
    }));

  return (
    <>
      <SimpleCard title={translate("recordCreate.startTitle")}>
        <SchemaFormFields
          operationId={operationId}
          only={["profile", ...plan.askedFields]}
          overrides={overrides}
        />
        {/* the schema pins fileIdentifier read-only (it is generated on every
            other write); the wizard offers it explicitly because the create
            serializer takes it and refuses a collision with a pointer error */}
        <TextInput
          source="fileIdentifier"
          label={translate("recordCreate.fileIdentifier")}
          helperText={translate("recordCreate.fileIdentifierHint")}
          fullWidth
        />
      </SimpleCard>
      <SimpleCard title={translate("recordCreate.templateTitle")}>
        <Stack spacing={1}>
          <FormControlLabel
            control={<Radio checked disabled />}
            label={translate("recordCreate.templateChoice")}
          />
          <Chip size="small" label={translate("recordCreate.templateComingSoon")} sx={{ width: "fit-content" }} />
          <Typography variant="body2">{translate("recordCreate.templateHint")}</Typography>
        </Stack>
      </SimpleCard>
      <CreatePlanPanel plan={plan} profileChosen={selectedId !== undefined && selectedId !== null && selectedId !== ""} />
    </>
  );
};

/**
 * The blank-record wizard of issue #1248: one screen for all three metadata
 * record types (their POST contract is identical), asking the mandatory
 * fields of the chosen profile through the schema-driven form. The template
 * choice of the mockup is deliberately NOT implemented — templates are the
 * next epic — so the row is rendered disabled and badged, which is a promise,
 * while an inert half-picker would be the lie.
 */
export const CreateMetadataRecord = () => {
  const resource = useResourceContext();
  const translate = useTranslate();
  // the profile endpoint answers no ordering parameters, so no `sort` field
  const profiles = useGetList(
    "MetadataProfile",
    {
      pagination: { page: 1, perPage: 100 },
      sort: { field: "", order: "ASC" },
    },
    { enabled: resource !== undefined },
  );
  return (
    <Create redirect="show">
      {profiles.isPending && <Alert severity="info">{translate("recordCreate.profileLoading")}</Alert>}
      {!profiles.isPending && (profiles.data ?? []).length === 0 && (
        <Alert severity="error">{translate("recordCreate.noProfiles")}</Alert>
      )}
      {!profiles.isPending && (profiles.data ?? []).length > 0 && (
        <SimpleForm toolbar={<CreateMetadataToolbar />}>
          <GlobalFormError />
          <WizardBody profiles={profiles.data ?? []} operationId={`create_${resource}`} />
        </SimpleForm>
      )}
    </Create>
  );
};

export default CreateMetadataRecord;
