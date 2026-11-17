import type { JsonApiDocument } from "../../../../jsonapi/types/jsonapi";

import type { ReactNode } from "react";
import { useId, useMemo, useState } from "react";
import {
  Button,
  type Identifier,
  type RaRecord,
  required,
  ResourceContextProvider,
  type Validator,
  SimpleForm,
  useDataProvider,
  useGetMany,
  useNotify,
  useRefresh,
  useTranslate,
  useUnselect,
} from "react-admin";

import {
  Alert,
  Box,
  Chip,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import axios from "axios";

import SchemaFormFields from "../../../../jsonapi/components/SchemaFormFields";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import useResourceSchema from "../../../../jsonapi/hooks/useResourceSchema";
import useSchemaRecordRepresentation from "../../../../jsonapi/hooks/useSchemaRecordRepresentation";
import Dialog from "../../../Dialog/Dialog";
import DialogHeader from "../../../Dialog/DialogHeader";
import useMappedElements from "./useMappedElements";
import { isSameValue, relatedIds, serializerFieldName } from "./values";

/**
 * The cap of records one batch run sends (acceptance criterion of #1249).
 *
 * Execution is synchronous, client-side, one ordinary json:api PATCH per
 * record by decision of the design review; the cap keeps a full run of the
 * dev deployment - where the write path runs the reverse mapper, the profile
 * rules and the publish seam per record - well below a minute. Measured on
 * that write path: a PATCH answers in ~0.1 s (median of 12 in-process
 * writes), so a capped run of 25 stays a few seconds even over the network.
 * A selection beyond the cap is guided to filter further instead of timing
 * out.
 */
export const BATCH_EDIT_MAX_RECORDS = 25;

type Phase = "change" | "preview" | "result";

type OutcomeStatus =
  "pending" | "applying" | "applied" | "rejected" | "skipped";

interface Outcome {
  status: OutcomeStatus;
  detail?: string;
}

/** The chip spelling of an outcome - stated once per status instead of a
 *  ternary chain the reader has to unwind. */
const outcomeChipColor = (status: OutcomeStatus) => {
  if (status === "applied") return "success" as const;
  if (status === "rejected") return "error" as const;
  if (status === "applying") return "primary" as const;
  return "default" as const;
};

const outcomeChipVariant = (status: OutcomeStatus) =>
  status === "applied" || status === "rejected" ? "filled" : "outlined";

interface BatchEditDialogProps {
  /** The json:api type of the selected records. */
  resource: string;
  /** The ids selected in the list; their records are read anew here. */
  ids: Identifier[];
  onClose: () => void;
}

/**
 * The batch edit over a selection of metadata records (#1249).
 *
 * One mapped element - a field the record's PATCH schema carries an
 * `x-iso-path` for - is edited once and written to every selected record the
 * user may edit, as ordinary sequential json:api PATCHes through the data
 * provider. Nothing bypasses the ordinary save path: every applied record
 * runs the validation (#1243), the write mapper and the publish seam (#1242,
 * #1244) exactly as a single edit does, which is why a partial failure is a
 * list of per-record results and not a rolled-back transaction.
 *
 * The dialog mirrors the 3-step shape of GeoNetwork's batch wizard
 * (selection -> change -> preview and apply), with the selection itself
 * belonging to the list and this dialog carrying the last two steps.
 */
const BatchEditDialog = ({ resource, ids, onClose }: BatchEditDialogProps) => {
  const translate = useTranslate();
  const formId = useId();
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const refresh = useRefresh();
  const unselect = useUnselect(resource);

  const elements = useMappedElements(resource);
  const operationId = `partial_update_${resource}`;
  const definitions = useFieldsForOperation({ operationId });
  const { includeAbleResources } = useResourceSchema(`list_${resource}`);

  const [elementSource, setElementSource] = useState<string>();
  const [phase, setPhase] = useState<Phase>("change");
  const [editValue, setEditValue] = useState<unknown>();
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [running, setRunning] = useState(false);
  const element = elements.find((item) => item.source === elementSource);

  const representation = useSchemaRecordRepresentation({
    resource: element?.reference,
  });

  // The current values are read anew for the chosen element - the list rows
  // are sparse and may be stale, and only this answer names `allowedActions`,
  // which is what keeps the run to the records the user may edit (#738). The
  // server still enforces the permission per request; this is courtesy,
  // never authority.
  const includeRef =
    element?.reference !== undefined &&
    includeAbleResources?.includes(element.source) === true;
  const jsonApiParams =
    element === undefined
      ? undefined
      : {
          [`fields[${resource}]`]: [
            "id",
            "title",
            "allowed_actions",
            serializerFieldName(element.source),
          ].join(","),
          ...(includeRef && {
            include: serializerFieldName(element.source),
            [`fields[${element.reference}]`]: "id,string_representation",
          }),
        };
  const current = useGetMany(
    resource,
    { ids, ...(jsonApiParams !== undefined && { meta: { jsonApiParams } }) },
    {
      enabled: element !== undefined,
      refetchOnMount: "always",
      retry: false,
    },
  );
  const records = useMemo(() => current.data ?? [], [current.data]);

  // the label of the value about to be written, when it names a related record
  const newRefIds =
    element?.reference !== undefined ? relatedIds(editValue) : [];
  const newRefs = useGetMany(
    element?.reference ?? resource,
    { ids: newRefIds },
    { enabled: newRefIds.length > 0 },
  );

  const rows = useMemo(
    () =>
      records.map((record) => {
        // the same courtesy rule as the retired canEdit: only an explicit
        // answer without "change" withholds the row (#738)
        const editable = record.allowedActions?.includes("change") ?? true;
        const unchanged =
          element !== undefined &&
          isSameValue(element, record[element.source], editValue);
        return { record, editable, unchanged, sends: editable && !unchanged };
      }),
    [records, element, editValue],
  );

  const sendable = rows.filter((row) => row.sends);
  const overCap = sendable.length > BATCH_EDIT_MAX_RECORDS;

  const formatValue = (value: unknown, store: RaRecord[] = []): ReactNode => {
    if (element === undefined) return undefined;
    if (value === undefined || value === null)
      return translate("batchEdit.noValue");
    if (element.reference !== undefined) {
      const items = (Array.isArray(value) ? value : [value]).filter(
        (item) => item != null,
      );
      if (items.length === 0) return translate("batchEdit.noValue");
      return (
        <Stack
          direction="row"
          spacing={0.5}
          useFlexGap
          sx={{ flexWrap: "wrap" }}
        >
          {items.map((item) => {
            const id = (item as RaRecord).id;
            const full = store.find((entry) => entry.id === id) ?? item;
            return (
              <Chip
                key={String(id)}
                size="small"
                variant="outlined"
                label={representation(full as RaRecord)}
              />
            );
          })}
        </Stack>
      );
    }
    if (typeof value === "boolean")
      return translate(value ? "batchEdit.yes" : "batchEdit.no");
    if (Array.isArray(value)) return value.map(String).join(", ");
    return String(value as string | number);
  };

  /** The json:api error objects of a refused PATCH, joined - the same answer
   *  a single edit surfaces in its form (#1243), listed per record here. */
  const errorDetail = (error: unknown): string => {
    if (axios.isAxiosError(error)) {
      const errors = (error.response?.data as JsonApiDocument | undefined)
        ?.errors;
      if (errors !== undefined && errors.length > 0) {
        const details = errors
          .map((object) => object.detail)
          .filter((detail) => detail !== undefined && detail !== "");
        if (details.length > 0) return details.join(" · ");
      }
      if (error.response?.status !== undefined)
        return translate("batchEdit.httpError", {
          status: error.response.status,
        });
    }
    return error instanceof Error && error.message !== ""
      ? error.message
      : String(error);
  };

  const submitChange = (values: Record<string, unknown>) => {
    if (element === undefined) return;
    setEditValue(values[element.source]);
    setPhase("preview");
  };

  const apply = async () => {
    if (element === undefined || running || overCap) return;
    setPhase("result");
    setRunning(true);
    let results: Record<string, Outcome> = {};
    for (const row of rows) {
      results[String(row.record.id)] = row.sends
        ? { status: "pending" }
        : {
            status: "skipped",
            detail: !row.editable
              ? translate("batchEdit.notEditable")
              : translate("batchEdit.unchanged"),
          };
    }
    setOutcomes(results);
    let applied = 0;
    let rejected = 0;
    for (const row of sendable) {
      const key = String(row.record.id);
      results = { ...results, [key]: { status: "applying" } };
      setOutcomes(results);
      try {
        // sequential on purpose by decision of #1249: every record is
        // validated and answered on its own, its chip updates in order, and a
        // run must not hit the write path concurrently
        const params = {
          id: row.record.id,
          data: { [element.source]: editValue },
          previousData: row.record,
        };
        await dataProvider.update(resource, params); // NOSONAR S9382 - the parallelism it asks for is what this design deliberately does not want
        applied += 1;
        results = { ...results, [key]: { status: "applied" } };
      } catch (error) {
        rejected += 1;
        results = {
          ...results,
          [key]: { status: "rejected", detail: errorDetail(error) },
        };
      }
      setOutcomes(results);
    }
    setRunning(false);
    notify("batchEdit.result", {
      type: rejected > 0 ? "warning" : "success",
      messageArgs: { applied, rejected },
    });
    // the records which were written, skipped or refused leave the selection;
    // rejected ones stay selected so a narrowed run can retry them
    const resolved = rows
      .filter((row) => results[String(row.record.id)]?.status !== "rejected")
      .map((row) => row.record.id);
    unselect(resolved);
    refresh();
  };

  const close = () => {
    if (!running) onClose();
  };

  const submitButton = (
    <Button
      label="batchEdit.preview"
      type="submit"
      form={formId}
      variant="contained"
      disabled={element === undefined || current.isPending || !!current.error}
    />
  );

  const actions = (() => {
    if (phase === "change") {
      return (
        <>
          <Button label="ra.action.cancel" onClick={close} />
          {submitButton}
        </>
      );
    }
    if (phase === "preview") {
      return (
        <>
          <Button label="batchEdit.back" onClick={() => setPhase("change")} />
          <Button
            label={translate("batchEdit.apply", {
              smart_count: sendable.length,
            })}
            onClick={apply}
            variant="contained"
            disabled={overCap || sendable.length === 0}
          />
        </>
      );
    }
    return (
      <Button label="ra.action.close" onClick={onClose} disabled={running} />
    );
  })();

  const outcomeCell = (record: RaRecord): ReactNode => {
    const outcome = outcomes[String(record.id)];
    if (outcome === undefined) return undefined;
    return (
      <Stack spacing={0.5} sx={{ minWidth: 140 }}>
        <Chip
          size="small"
          color={outcomeChipColor(outcome.status)}
          variant={outcomeChipVariant(outcome.status)}
          label={translate(`batchEdit.outcome.${outcome.status}`)}
        />
        {outcome.detail !== undefined && (
          <Typography
            variant="caption"
            color={
              outcome.status === "rejected" ? "error.main" : "text.secondary"
            }
          >
            {outcome.detail}
          </Typography>
        )}
      </Stack>
    );
  };

  const doneCount = sendable.filter((row) =>
    ["applied", "rejected"].includes(
      outcomes[String(row.record.id)]?.status ?? "",
    ),
  ).length;

  const omitSources = definitions
    .map((definition) => definition.props.source)
    .filter((source) => source !== elementSource);

  // the one chosen element's schema input, required: a batch always writes a value
  const overrides =
    element === undefined
      ? undefined
      : [
          {
            component: element.definition.component,
            props: {
              ...element.definition.props,
              validate: [
                ...((element.definition.props.validate as Validator[]) ?? []),
                required(),
              ],
            },
          },
        ];

  return (
    <ResourceContextProvider value={resource}>
      {/* the form sits outside the dialog shell: inside it, MUI's dialog breaks scrolling */}
      <SimpleForm id={formId} onSubmit={submitChange} toolbar={false}>
        <Dialog
          open
          onClose={close}
          maxWidth="md"
          title={
            <DialogHeader onClose={close}>
              {translate("batchEdit.title", { smart_count: ids.length })}
            </DialogHeader>
          }
          actions={actions}
        >
          <Stack spacing={2} sx={{ minWidth: 480 }}>
            <Typography variant="body2" color="text.secondary">
              {translate("batchEdit.description")}
            </Typography>
            <Stepper activeStep={phase === "change" ? 1 : 2}>
              <Step>
                <StepLabel>{translate("batchEdit.stepSelection")}</StepLabel>
              </Step>
              <Step>
                <StepLabel>{translate("batchEdit.stepChange")}</StepLabel>
              </Step>
              <Step>
                <StepLabel>{translate("batchEdit.stepPreview")}</StepLabel>
              </Step>
            </Stepper>

            {phase === "change" && (
              <>
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    {translate("batchEdit.element")}
                  </Typography>
                  <Select
                    value={elementSource ?? ""}
                    displayEmpty
                    fullWidth
                    onChange={(event) => setElementSource(event.target.value)}
                    renderValue={(value) =>
                      value === ""
                        ? translate("batchEdit.elementPlaceholder")
                        : (elements.find((item) => item.source === value)
                            ?.label ?? value)
                    }
                  >
                    <MenuItem value="" disabled>
                      {translate("batchEdit.elementPlaceholder")}
                    </MenuItem>
                    {elements.map((item) => (
                      <MenuItem key={item.source} value={item.source}>
                        {item.label}
                      </MenuItem>
                    ))}
                  </Select>
                  {element !== undefined && (
                    <Typography variant="caption" color="text.secondary">
                      {translate("batchEdit.isoPath", {
                        path: element.isoPath,
                      })}
                    </Typography>
                  )}
                </Box>
                {element !== undefined && (
                  <SchemaFormFields
                    operationId={operationId}
                    omit={omitSources}
                    overrides={overrides}
                    record={{ id: "batch" }}
                  />
                )}
                <Alert severity="info">{translate("batchEdit.info")}</Alert>
              </>
            )}

            {(phase === "preview" || phase === "result") && (
              <>
                {overCap && (
                  <Alert severity="warning">
                    {translate("batchEdit.capGuidance", {
                      max: BATCH_EDIT_MAX_RECORDS,
                    })}
                  </Alert>
                )}
                {phase === "result" && (
                  <Box>
                    <LinearProgress
                      variant="determinate"
                      value={
                        sendable.length === 0
                          ? 100
                          : Math.round((doneCount / sendable.length) * 100)
                      }
                    />
                    <Typography variant="caption" color="text.secondary">
                      {translate("batchEdit.progress", {
                        done: doneCount,
                        total: sendable.length,
                      })}
                    </Typography>
                  </Box>
                )}
                <Box sx={{ maxHeight: 420, overflowY: "auto" }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{translate("batchEdit.record")}</TableCell>
                        <TableCell>{translate("batchEdit.now")}</TableCell>
                        <TableCell>{translate("batchEdit.after")}</TableCell>
                        {phase === "result" && (
                          <TableCell>{translate("batchEdit.status")}</TableCell>
                        )}
                        {phase === "preview" && <TableCell />}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row) => (
                        <TableRow key={String(row.record.id)}>
                          <TableCell>
                            {row.record.title ??
                              row.record.stringRepresentation ??
                              row.record.id}
                          </TableCell>
                          <TableCell>
                            {formatValue(
                              element !== undefined
                                ? row.record[element.source]
                                : undefined,
                            )}
                          </TableCell>
                          <TableCell>
                            {formatValue(editValue, newRefs.data ?? [])}
                          </TableCell>
                          {phase === "result" && (
                            <TableCell>{outcomeCell(row.record)}</TableCell>
                          )}
                          {phase === "preview" && (
                            <TableCell>
                              {!row.editable && (
                                <Chip
                                  size="small"
                                  variant="outlined"
                                  label={translate("batchEdit.notEditable")}
                                />
                              )}
                              {row.editable && row.unchanged && (
                                <Chip
                                  size="small"
                                  variant="outlined"
                                  label={translate("batchEdit.unchanged")}
                                />
                              )}
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
                {!running && rows.length < ids.length && (
                  <Alert severity="info">
                    {translate("batchEdit.staleSelection")}
                  </Alert>
                )}
              </>
            )}

            {phase === "preview" && current.isPending && <LinearProgress />}
            {current.error !== null && current.error !== undefined && (
              <Alert severity="error">{translate("batchEdit.loadError")}</Alert>
            )}
          </Stack>
        </Dialog>
      </SimpleForm>
    </ResourceContextProvider>
  );
};

export default BatchEditDialog;
