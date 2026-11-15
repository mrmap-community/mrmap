/**
 * The full screen record editor (#1245).
 *
 * The editor is a route (`/metadata/:type/:id/edit`), not a dialog: the
 * section rail, the sticky toolbar and the findings rail need the whole
 * screen, and a route survives navigation the way a dialog does not. It is
 * built from the react-admin building blocks — `Edit` for the record fetch
 * and the validated write, a form for the values, `SchemaFormFields`-style
 * schema definitions for the inputs — and only the rails are own components,
 * which react-admin has no equivalent of (decided in the review of #1238).
 *
 * Grouping, labels and the mandatory flags come from the record's profile
 * (#1240) fetched with the record via `include=profile`; ISO paths come from
 * the `x-iso-path` extension of the schema. The findings rail pre-validates
 * the profile's rules against the current values and, after a refused save,
 * shows the server's verdict — the client's copy of a rule is matched to the
 * server's finding by the rule id #1243 cites.
 *
 * There is no draft/publish split: a validated save IS the publish (#1244,
 * decided in the review of #1238), which is why the toolbar carries the
 * single save action.
 */

import type { FieldDefinition } from "../../../../jsonapi/utils";
import type {
  EditorMode,
  EditorSection,
  Finding,
  ProfileData,
  ProfileSection,
} from "./types";

import {
  createElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import {
  Edit,
  required,
  SaveButton,
  SimpleForm,
  useGetRecordRepresentation,
  useNotify,
  useRecordContext,
  useTranslate,
  type HttpError,
} from "react-admin";
import { useFormState, useWatch } from "react-hook-form";

import { Alert, Box, Chip, Stack, Typography } from "@mui/material";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";

import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import useResourceSchema from "../../../../jsonapi/hooks/useResourceSchema";
import SimpleCard from "../../../MUI/SimpleCard";
import RecordContacts from "../RecordShow/RecordContacts";
import RecordFields from "../RecordShow/RecordFields";
import RecordHistory from "../RecordShow/RecordHistory";
import RecordRelations from "../RecordShow/RecordRelations";
import FindingsRail from "./FindingsRail";
import {
  clientFindings,
  completeness,
  mergeFindings,
  serverFindings,
} from "./rules";
import {
  buildEditorSections,
  flattenSectionFields,
  sectionOfField,
} from "./sections";
import SectionsRail, {
  type RailCounts,
  type RailItem,
} from "./SectionsRail";

// the related instances the editor's inputs and the reused read-only cards
// render — the same set `RecordShow` asks for, plus the profile whose
// sections and rules drive the editor itself (#1243's include decision)
const RECORD_INCLUDES = [
  "profile",
  "metadataContact",
  "datasetContact",
  "applicationContact",
  "licence",
  "keywords",
  "referenceSystems",
  "timeExtents",
  "languages",
  "categories",
  "harvestedThrough",
  "createdBy",
  "lastModifiedBy",
];

// the read-only areas of the rail: they reuse the RecordShow cards and their
// translation keys instead of a second overview
const READONLY_CONTACTS = "readonly-contacts";
const READONLY_RELATIONS = "readonly-relations";
const READONLY_HARVESTS = "readonly-harvests";
const READONLY_HISTORY = "readonly-history";

const lastElement = (path: string): string => path.split("/").pop() ?? path;

// the property shape of the write component, read only far enough to see the
// `x-iso-path` stamp (#1240's postprocessing) and the array-ness of values
// and to-many relationships (#1245's cardinality chips)
interface SchemaProperty {
  "x-iso-path"?: string;
  type?: string;
  properties?: Record<string, SchemaProperty | undefined>;
}

interface EditorContentProps {
  type: string;
  mode: EditorMode;
  onModeChange: (next: EditorMode) => void;
  showIsoPaths: boolean;
  onToggleIsoPaths: (next: boolean) => void;
  active: string | undefined;
  onSelect: (id: string) => void;
  serverFindings: Finding[];
  focus: { field: string; nonce: number } | undefined;
  onFocusField: (field: string) => void;
}

/** one writable field: its schema input, with the profile's demands applied */
const EditorFieldRow = ({
  field,
  showIsoPaths,
  validate,
  requiredFlag,
}: {
  field: EditorFieldLike;
  showIsoPaths: boolean;
  validate: unknown[] | undefined;
  requiredFlag: boolean;
}): ReactElement => {
  const translate = useTranslate();
  const { definition } = field;
  const isoHint =
    showIsoPaths && field.isoPath
      ? translate("metadataEditor.writtenTo", { path: field.isoPath })
      : undefined;
  const helperText = isoHint ? (
    <>
      {definition.props.helperText ?? null}
      <Box
        component="div"
        sx={{ fontFamily: "monospace", fontSize: 12, color: "text.secondary" }}
      >
        {isoHint}
      </Box>
    </>
  ) : (
    definition.props.helperText
  );
  return (
    <Box data-editor-field={field.source}>
      {createElement(definition.component, {
        ...definition.props,
        ...(requiredFlag && { required: true }),
        ...(validate && validate.length > 0 && { validate }),
        ...(helperText !== undefined && { helperText }),
      })}
    </Box>
  );
};

// the EditorField type from ./types carries the definition; this alias keeps
// the row component readable without importing the whole namespace
type EditorFieldLike = EditorSection["groups"][number]["fields"][number];

interface SectionPaneProps {
  section: EditorSection;
  mode: EditorMode;
  showIsoPaths: boolean;
}

/** the fields of one section; Advanced mode groups them by ISO element */
const SectionPane = ({
  section,
  mode,
  showIsoPaths,
}: SectionPaneProps): ReactElement => {
  const fields =
    mode === "advanced"
      ? section.groups
      : [{ elementPath: undefined, fields: flattenSectionFields(section) }];
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Typography variant="h5" component="h2">
        {section.label}
      </Typography>
      {fields.map((group, index) =>
        mode === "advanced" && group.elementPath ? (
          <SimpleCard
            key={`${group.elementPath}:${index}`}
            title={
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", flexWrap: "wrap" }}
              >
                <Typography variant="h6">
                  {lastElement(group.elementPath)}
                </Typography>
                {group.cardinality && (
                  <Chip size="small" label={group.cardinality} />
                )}
              </Stack>
            }
            contentProps={{
              sx: { display: "flex", flexDirection: "column", gap: 2 },
            }}
          >
            {group.fields.map((field) => (
              <EditorFieldRow
                key={field.source}
                field={field}
                showIsoPaths={showIsoPaths}
                validate={
                  field.requirement === "mandatory"
                    ? [required(), ...(definitionValidate(field) ?? [])]
                    : definitionValidate(field)
                }
                requiredFlag={field.requirement === "mandatory"}
              />
            ))}
          </SimpleCard>
        ) : (
          <Stack key={`group:${index}`} spacing={2}>
            {group.fields.map((field) => (
              <EditorFieldRow
                key={field.source}
                field={field}
                showIsoPaths={showIsoPaths}
                validate={
                  field.requirement === "mandatory"
                    ? [required(), ...(definitionValidate(field) ?? [])]
                    : definitionValidate(field)
                }
                requiredFlag={field.requirement === "mandatory"}
              />
            ))}
          </Stack>
        ),
      )}
    </Stack>
  );
};

const definitionValidate = (
  field: EditorFieldLike,
): unknown[] | undefined =>
  field.definition.props.validate as unknown[] | undefined;

/**
 * The toolbar of the editor, INSIDE the form element: the unsaved indicator
 * reads the form state and the save button submits the form, which is what
 * runs the validators and the write. It sticks so it survives a long section.
 */
const EditorToolbar = ({
  showIsoPaths,
  onToggleIsoPaths,
}: {
  showIsoPaths: boolean;
  onToggleIsoPaths: (next: boolean) => void;
}): ReactElement => {
  const translate = useTranslate();
  const { dirtyFields } = useFormState({});
  const dirtyCount = Object.values(dirtyFields ?? {}).filter(Boolean).length;
  return (
    <Stack
      direction="row"
      useFlexGap
      sx={{
        justifyContent: "space-between",
        alignItems: "center",
        position: "sticky",
        top: 0,
        zIndex: "prompt",
        bgcolor: "background.paper",
        py: 1,
        px: 1,
        borderBottom: 1,
        borderColor: "divider",
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <Box
          aria-hidden
          sx={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            bgcolor: dirtyCount > 0 ? "warning.main" : "success.main",
          }}
        />
        <Typography variant="body2">
          {dirtyCount > 0
            ? translate("metadataEditor.unsavedChanges", {
                smart_count: dirtyCount,
              })
            : translate("metadataEditor.allSaved")}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <ToggleButton
          size="small"
          value="iso"
          selected={showIsoPaths}
          onClick={() => onToggleIsoPaths(!showIsoPaths)}
          sx={{ textTransform: "none" }}
        >
          {translate("metadataEditor.isoToggle")}
        </ToggleButton>
        <SaveButton label="metadataEditor.saveAndPublish" />
      </Stack>
    </Stack>
  );
};

interface EditorPanesProps {
  sections: EditorSection[];
  readOnly: RailItem[];
  active: string;
  onSelect: (id: string) => void;
  mode: EditorMode;
  showIsoPaths: boolean;
  rules: ProfileData["rules"];
  isoPaths: Record<string, string>;
  serverFindings: Finding[];
  focus: { field: string; nonce: number } | undefined;
  onFocusField: (field: string) => void;
  readOnlyPane: ReactNode;
  sourceCard: ReactNode;
}

/**
 * The three panes inside the form: the rail's badges and the findings are
 * computed from the live values, which only exist inside the form context.
 */
const EditorPanes = ({
  sections,
  readOnly,
  active,
  onSelect,
  mode,
  showIsoPaths,
  rules,
  isoPaths,
  serverFindings: server,
  focus,
  onFocusField,
  readOnlyPane,
  sourceCard,
}: EditorPanesProps): ReactElement => {
  const values = (useWatch() ?? {}) as Record<string, unknown>;

  const findings = useMemo(
    () => mergeFindings(clientFindings(rules, values), server),
    [rules, values, server],
  );

  const counts = useMemo(() => {
    const result: Record<string, RailCounts> = {};
    for (const section of sections) {
      const sources = new Set(
        flattenSectionFields(section).map((field) => field.source),
      );
      const scoped = findings.filter(
        (finding) => finding.field && sources.has(finding.field),
      );
      result[section.id] = {
        errors: scoped.filter((finding) => finding.severity === "error").length,
        warnings: scoped.length - scoped.filter((finding) => finding.severity === "error").length,
      };
    }
    return result;
  }, [sections, findings]);

  const profileCompleteness = useMemo(
    () =>
      completeness(
        sections.flatMap((section) => section.mandatory),
        values,
      ),
    [sections, values],
  );

  // the findings rail names a field; jumping means switching to its section
  // first and focusing the input once the pane has rendered it
  const paneRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!focus) return;
    const target = paneRef.current?.querySelector(
      `[data-editor-field="${focus.field}"]`,
    );
    if (!target) return;
    target.scrollIntoView({ block: "center" });
    const input = target.querySelector(
      'input, textarea, [role="combobox"]',
    ) as HTMLElement | null;
    input?.focus();
  }, [focus, active]);

  const activeSection = sections.find((section) => section.id === active);

  return (
    <Stack
      direction="row"
      spacing={3}
      sx={{ alignItems: "flex-start", width: "100%" }}
    >
      <SectionsRail
        sections={sections.map((section) => ({
          id: section.id,
          label: section.label,
        }))}
        readOnly={readOnly}
        active={active}
        onSelect={onSelect}
        counts={counts}
        completeness={profileCompleteness}
      />
      <Box ref={paneRef} sx={{ flexGrow: 1, minWidth: 0, width: "100%" }}>
        {activeSection ? (
          <SectionPane
            section={activeSection}
            mode={mode}
            showIsoPaths={showIsoPaths}
          />
        ) : (
          readOnlyPane
        )}
      </Box>
      <FindingsRail
        findings={findings}
        isoPaths={isoPaths}
        onJump={(finding) => {
          if (finding.field) onFocusField(finding.field);
        }}
        sourceCard={sourceCard}
      />
    </Stack>
  );
};

const EditorContent = ({
  type,
  mode,
  onModeChange,
  showIsoPaths,
  onToggleIsoPaths,
  active,
  onSelect,
  serverFindings: server,
  focus,
  onFocusField,
}: EditorContentProps): ReactElement | null => {
  const record = useRecordContext();
  const translate = useTranslate();
  const representation = useGetRecordRepresentation(type);
  const definitions = useFieldsForOperation({
    operationId: `partial_update_${type}`,
  });
  const { schema } = useResourceSchema(`partial_update_${type}`);
  const historicalOperation = useOperation(`list_Historical${type}`);

  // the ISO paths and the array-ness come from the same operation component
  // whose properties carry `x-iso-path` (#1240's postprocessing hook)
  const { isoPaths, repeatableSources } = useMemo(() => {
    const properties = schema?.properties as
      | Record<string, SchemaProperty | undefined>
      | undefined;
    const attributes = properties?.attributes?.properties ?? {};
    const relationships = properties?.relationships?.properties ?? {};
    const paths: Record<string, string> = {};
    const repeatable: string[] = [];
    for (const [name, property] of Object.entries(attributes)) {
      if (typeof property?.["x-iso-path"] === "string")
        paths[name] = property["x-iso-path"];
      if (property?.type === "array") repeatable.push(name);
    }
    for (const [name, property] of Object.entries(relationships)) {
      if (typeof property?.["x-iso-path"] === "string")
        paths[name] = property["x-iso-path"];
      if (property?.properties?.data?.type === "array") repeatable.push(name);
    }
    return { isoPaths: paths, repeatableSources: repeatable };
  }, [schema]);

  const profile = (record?.profile ?? undefined) as ProfileData | undefined;
  const profileSections = Array.isArray(profile?.sections)
    ? (profile.sections as ProfileSection[])
    : [];
  const sections = useMemo(
    () =>
      buildEditorSections({
        // without a seeded profile the editor still edits: every writable
        // schema field forms one flat section and the server keeps the rules
        sections:
          profileSections.length > 0
            ? profileSections
            : [
                {
                  id: "fields",
                  label: translate("metadataEditor.fieldsSection"),
                  fields: definitions
                    .filter((definition) => !definition.props.disabled)
                    .map((definition) => ({
                      field: definition.props.source,
                      requirement: "recommended" as const,
                    })),
                },
              ],
        definitions,
        isoPaths,
        repeatableSources,
        mode,
        otherLabel: translate("metadataEditor.otherElements"),
      }),
    [profileSections, definitions, isoPaths, repeatableSources, mode, translate],
  );

  if (!record) return null;

  const readOnlyItems: RailItem[] = [
    { id: READONLY_CONTACTS, label: translate("recordShow.contacts") },
    { id: READONLY_RELATIONS, label: translate("recordShow.relations") },
    { id: READONLY_HARVESTS, label: translate("recordShow.harvests") },
    ...(historicalOperation
      ? [{ id: READONLY_HISTORY, label: translate("recordShow.history") }]
      : []),
  ];

  const available = [
    ...sections.map((section) => section.id),
    ...readOnlyItems.map((item) => item.id),
  ];
  const effectiveActive =
    active && available.includes(active) ? active : available[0];

  const readOnlyPane =
    effectiveActive === READONLY_CONTACTS ? (
      <RecordContacts />
    ) : effectiveActive === READONLY_RELATIONS ? (
      <Stack spacing={1} sx={{ minWidth: 0 }}>
        <Typography variant="body2" color="text.secondary">
          {translate("metadataEditor.relationsReadonly")}
        </Typography>
        <RecordRelations />
      </Stack>
    ) : effectiveActive === READONLY_HARVESTS ? (
      <RecordHistory harvests />
    ) : effectiveActive === READONLY_HISTORY ? (
      <RecordHistory />
    ) : undefined;

  const sourceCard = (
    <SimpleCard title={translate("metadataEditor.sourceCard")}>
      <RecordFields
        sources={["origin", "harvestedThrough", "originUrl"]}
      />
      {record.isCustomized && (
        <Typography variant="caption" color="text.secondary">
          {translate("metadataEditor.customizedHint")}
        </Typography>
      )}
    </SimpleCard>
  );

  const header = (
    <Stack spacing={1} sx={{ p: 2, overflowWrap: "anywhere" }}>
      <Typography variant="h5">{representation(record)}</Typography>
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1 }}>
        {profile?.label && (
          <Chip
            size="small"
            variant="outlined"
            color="primary"
            label={`${profile.name ?? "iso19139"} \u00b7 ${profile.label}`}
          />
        )}
        <Chip
          size="small"
          color={record.isSearchable ? "success" : "default"}
          label={translate(
            record.isSearchable
              ? "recordShow.searchable"
              : "recordShow.unpublished",
          )}
        />
        {record.isCustomized && (
          <Chip size="small" label={translate("recordShow.writtenAgain")} />
        )}
      </Stack>
    </Stack>
  );

  // a record the user may not edit is not edited: the read-only areas stay
  // readable, exactly as the show screen leaves them (#1241's canEdit rule)
  if (!record.canEdit)
    return (
      <Stack spacing={2}>
        {header}
        <Alert severity="warning">
          {translate("metadataEditor.noPermission")}
        </Alert>
        <Stack direction="row" spacing={3} sx={{ px: 2, alignItems: "flex-start" }}>
          <SectionsRail
            sections={[]}
            readOnly={readOnlyItems}
            active={effectiveActive ?? ""}
            onSelect={onSelect}
            counts={{}}
          />
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>{readOnlyPane}</Box>
        </Stack>
      </Stack>
    );

  // the read-only cards reused inside the form carry plain buttons; inside a
  // <form> element a button without a type submits it, so the pane swallows
  // their activation instead of letting the editor save itself
  const readOnlyGuarded = readOnlyPane ? (
    <Box
      onClickCapture={(event) => {
        if ((event.target as HTMLElement).closest("button"))
          event.preventDefault();
      }}
      onKeyDownCapture={(event) => {
        if (
          event.key === "Enter" &&
          (event.target as HTMLElement).closest("button")
        )
          event.preventDefault();
      }}
      sx={{ minWidth: 0 }}
    >
      {readOnlyPane}
    </Box>
  ) : undefined;

  return (
    <Stack spacing={1}>
      {header}
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: "center", px: 2, pt: 1 }}
      >
        <ToggleButtonGroup
          exclusive
          size="small"
          value={mode}
          onChange={(_, next: EditorMode | null) => next && onModeChange(next)}
        >
          <ToggleButton value="simple" sx={{ textTransform: "none" }}>
            {translate("metadataEditor.simple")}
          </ToggleButton>
          <ToggleButton value="advanced" sx={{ textTransform: "none" }}>
            {translate("metadataEditor.advanced")}
          </ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="caption" color="text.secondary">
          {translate("metadataEditor.modeHint")}
        </Typography>
      </Stack>
      <SimpleForm toolbar={false} sanitizeEmptyValues>
        <EditorToolbar
          showIsoPaths={showIsoPaths}
          onToggleIsoPaths={onToggleIsoPaths}
        />
        <EditorPanes
          sections={sections}
          readOnly={readOnlyItems}
          active={effectiveActive ?? ""}
          onSelect={onSelect}
          mode={mode}
          showIsoPaths={showIsoPaths}
          rules={profile?.rules}
          isoPaths={isoPaths}
          serverFindings={server}
          focus={focus}
          onFocusField={(field) => {
            const section = sectionOfField(sections, field);
            if (section) onSelect(section.id);
            onFocusField(field);
          }}
          readOnlyPane={readOnlyGuarded}
          sourceCard={sourceCard}
        />
      </SimpleForm>
    </Stack>
  );
};

interface MetadataEditorProps {
  type: string;
}

const MetadataEditor = ({ type }: MetadataEditorProps): ReactElement => {
  const notify = useNotify();
  const [mode, setMode] = useState<EditorMode>("simple");
  const [showIsoPaths, setShowIsoPaths] = useState(false);
  const [active, setActive] = useState<string | undefined>(undefined);
  const [focus, setFocus] = useState<
    { field: string; nonce: number } | undefined
  >(undefined);
  const [server, setServer] = useState<Finding[]>([]);

  const { includeAbleResources, sparseFieldsPerResource } =
    useResourceSchema(`retrieve_${type}`);
  const definitions = useFieldsForOperation({
    operationId: `partial_update_${type}`,
  });

  // the record arrives with its profile (whose rules and sections drive the
  // editor) and with the related instances the inputs and the read-only
  // cards render — filtered by what the endpoint actually allows to include
  const queryMeta = useMemo(() => {
    const wanted = [
      ...RECORD_INCLUDES,
      ...definitions
        .filter(
          (definition: FieldDefinition) =>
            definition.component === SchemaAutocompleteInput,
        )
        .map((definition: FieldDefinition) => definition.props.source as string),
    ];
    const include = includeAbleResources
      ? wanted.filter((name) => includeAbleResources.includes(name))
      : wanted;
    const jsonApiParams: Record<string, string> = {
      include: include.join(","),
    };
    if (sparseFieldsPerResource) {
      for (const name of include) {
        if (RECORD_INCLUDES.includes(name) || name === "profile") continue;
        jsonApiParams[`fields[${name}]`] = "id,string_representation";
      }
    }
    return { jsonApiParams };
  }, [definitions, includeAbleResources, sparseFieldsPerResource]);

  return (
    <Edit
      resource={type}
      redirect={false}
      mutationMode="pessimistic"
      title={false}
      queryOptions={{ meta: queryMeta }}
      mutationOptions={{
        onSuccess: () => {
          setServer([]);
          notify("metadataEditor.saved", { type: "success" });
        },
        onError: (error: Error) => {
          const body = (error as HttpError).body as
            | { jsonApiErrors?: unknown[] }
            | undefined;
          if (Array.isArray(body?.jsonApiErrors) && body.jsonApiErrors.length) {
            setServer(serverFindings(body.jsonApiErrors));
          } else {
            notify("metadataEditor.saveFailed", { type: "error" });
          }
        },
      }}
    >
      <EditorContent
        type={type}
        mode={mode}
        showIsoPaths={showIsoPaths}
        active={active}
        onSelect={setActive}
        serverFindings={server}
        focus={focus}
        onFocusField={(field) =>
          setFocus((previous) => ({ field, nonce: (previous?.nonce ?? 0) + 1 }))
        }
        onModeChange={setMode}
        onToggleIsoPaths={setShowIsoPaths}
      />
    </Edit>
  );
};

export default MetadataEditor;
