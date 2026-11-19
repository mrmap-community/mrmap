import type { CustomMethod } from "../../../../providers/dataProvider";

import { useState, type ReactNode } from "react";
import {
  HttpError,
  useDataProvider,
  useRecordContext,
  useTranslate,
  type Identifier,
} from "react-admin";
import { useFormContext, useWatch } from "react-hook-form";

import { Alert, Button, Stack, Typography } from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";
/** The periodic operation whose schedule the form configures; it selects
 * the crontab field of the form and names the operation in the preview
 * request, mirroring `operation` of the backend draft contract (#1327). */
export type SchedulePreviewOperation = "monitoring" | "update" | "harvest";

/** What the preview endpoint answers next to a proposal (registry
 * `SchedulingPreview`); every number is honest-null and only means what its
 * evidence allows - a null duration is not zero (#1325, #1327). */
export interface SchedulePreviewAnswer {
  id: string;
  operation: string;
  serviceKind: string;
  serviceId: string;
  settingId: number | null;
  scheduling: string | null;
  enabled: boolean;
  nextOccurrences: string[];
  intervalSeconds: number | null;
  potentialOverlap: boolean | null;
  overlapBasis: string | null;
  elapsed: {
    evidence: string;
    p50Seconds: number | null;
    p95Seconds: number | null;
    averageSeconds: number | null;
    sampleCount: number;
    p95MinimumSamples: number;
    failedCount: number;
    incompleteCount: number;
    lookbackDays: number;
    lastMeasurementAt: string | null;
  };
  warningCodes: string[];
  warnings: { code: string; message: string }[];
  /** the capacity section of the estimate, in whatever shape the backend
   * answers it; null is the answer that no capacity was computable */
  capacity: unknown;
  capacityReason: string;
  /** the cadence-preserving alternatives of #1328; empty whenever the
   * engine refused, and a refusal carries its reason below */
  suggestions: ScheduleSuggestion[];
  suggestionsReason: string | null;
  suggestionsReasonCode: string | null;
  suggestionsHorizonDays: number | null;
  settingRevision: string | null;
  asOf: string;
  expiresAt: string;
}

/** One cadence-preserving alternative of #1328: an entire crontab which
 * fires exactly as often as the answered proposal over the evaluated
 * horizon - the count was verified for both by the canonical Beat walk -
 * ranked by the measured worker-seconds of the deployment snapshot. The
 * numbers are a measured preference, never a claim of a free slot. */
export interface ScheduleSuggestion {
  crontab: string;
  timezone: string;
  horizonDays: number;
  horizonStart: string;
  horizonEnd: string;
  firingCount: number;
  queue: string;
  originalWorkerSeconds: number;
  expectedWorkerSeconds: number;
  sampleCount: number;
  costCoverage: number;
  snapshotAt: string;
  reason: string;
}

export interface SchedulePreviewPanelProps {
  operation: SchedulePreviewOperation;
  /** the kind of service the schedule belongs to; when the injection site
   * knows it (its own show screen does), pass it, otherwise the panel reads
   * the form's service relationship which must then carry it */
  serviceKind?: string;
  /** the service the schedule belongs to; the schedule screens inject the
   * service of their show context, an edit dialog falls back to the form's
   * `service` value */
  serviceId?: Identifier;
}

/** the crontab source the form of this operation family edits */
const CRONTAB_SOURCE: Record<SchedulePreviewOperation, string> = {
  monitoring: "scheduleInterval",
  update: "scheduleInterval",
  harvest: "scheduling",
};

/** how many coming occurrences the panel spells out */
const SHOWN_OCCURRENCES = 3;

const formatSeconds = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) {
    const minutes = seconds / 60;
    return `${minutes < 10 ? minutes.toFixed(1) : Math.round(minutes)} min`;
  }
  return `${(seconds / 3600).toFixed(1)} h`;
};

const formatMoment = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));

/** the readable detail of a rejected preview: the mapped json:api field
 * errors when the provider answered them, the plain message otherwise */
const errorDetail = (error: unknown): string => {
  if (error instanceof HttpError) {
    const errors = (
      error.body as { errors?: Record<string, string | { serverError?: string }> } | undefined
    )?.errors;
    const detail = errors
      ? Object.values(errors)
          .map((value) =>
            typeof value === "string" ? value : (value?.serverError ?? ""),
          )
          .filter((value) => value !== "")
          .join("\n")
      : undefined;
    if (detail !== undefined && detail !== "") return detail;
    return String(error.message);
  }
  return error instanceof Error ? error.message : String(error);
};

const Metric = ({ label, value }: { label: string; value: ReactNode }) => (
  <Stack
    direction="row"
    sx={{ justifyContent: "space-between" }}
    spacing={1}
  >
    <Typography variant="body2" color="text.secondary">
      {label}
    </Typography>
    <Typography variant="body2" component="span">
      {value}
    </Typography>
  </Stack>
);

/** The pre-save answer to "what would this schedule mean?": the coming
 * occurrences, the wait between them, the durations the service's completed
 * runs measured and the warnings of the proposal (#1327).
 *
 * Where the deployment's verified capacity data underpins it, the answer
 * also carries the cadence-preserving alternatives of #1328: entire crontabs
 * which fire exactly as often as the proposal, with the measured occupancy
 * they expect. Applying one takes an explicit click - the panel never
 * touches the form by itself - and where the engine refused, the answer
 * says why instead of showing an "empty-looking" minute.
 *
 * Asking is side-effect-free on both sides: the endpoint never persists and
 * this panel never submits the form - the preview is read-only information
 * beside the save, and none of its warnings blocks the save. The button is
 * deliberate: no request while the user is still typing, and a changed form
 * marks the answer as stale instead of silently re-asking.
 *
 * Renders inside the SimpleForm of a schedule dialog (injected as a
 * `referenceInputs` entry); it reads its draft from the surrounding form. */
const SchedulePreviewPanel = ({
  operation,
  serviceKind,
  serviceId,
}: SchedulePreviewPanelProps) => {
  const translate = useTranslate();
  const dataProvider = useDataProvider();
  const record = useRecordContext();
  const form = useFormContext();

  const [answer, setAnswer] = useState<SchedulePreviewAnswer | null>(null);
  const [askedDraft, setAskedDraft] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const values = (useWatch() ?? {}) as Record<string, unknown>;
  const service = values.service as
    | Identifier
    | { id?: Identifier }
    | undefined;
  const draft = {
    operation,
    serviceKind: serviceKind ?? "",
    serviceId:
      serviceId ??
      (service !== null && service !== undefined && typeof service === "object"
        ? service.id
        : service) ??
      "",
    // inside the edit dialog the record context is the setting itself
    settingId: record?.id,
    scheduling: (values[CRONTAB_SOURCE[operation]] as string) || undefined,
    enabled: values.enabled !== false,
  };
  const draftKey = JSON.stringify(draft);
  const previewable = draft.serviceKind !== "" && draft.serviceId !== "";
  const isStale = answer !== null && askedDraft !== draftKey;

  const ask = async () => {
    setLoading(true);
    setError(null);
    const attributes: Record<string, unknown> = {
      operation: draft.operation,
      serviceKind: draft.serviceKind,
      serviceId: String(draft.serviceId),
      enabled: draft.enabled,
    };
    if (draft.settingId !== undefined && draft.settingId !== null) {
      attributes.settingId = draft.settingId;
    }
    if (draft.scheduling) attributes.scheduling = draft.scheduling;
    const custom = dataProvider.custom as CustomMethod | undefined;
    if (custom === undefined) {
      setError("the data provider of this application answers no custom calls");
      setLoading(false);
      return;
    }
    try {
      const { data } = await custom<SchedulePreviewAnswer>(
        "preview_scheduling",
        {
          method: "POST",
          body: { data: { type: "SchedulingPreview", attributes } },
        },
      );
      setAnswer(data);
      setAskedDraft(draftKey);
    } catch (error_) {
      setAnswer(null);
      setAskedDraft(null);
      setError(errorDetail(error_));
    } finally {
      setLoading(false);
    }
  };

  /** Writes one alternative into the crontab field of the form. This is the
   * only way a suggestion reaches the schedule: an explicit click. What the
   * form carries beside the five cadence fields - its timezone suffix - is
   * kept, a suggestion never moves the zone. */
  const apply = (suggestion: ScheduleSuggestion) => {
    const source = CRONTAB_SOURCE[operation];
    const carried = (values[source] as string | undefined) ?? "";
    const suffix = carried
      .trim()
      .split(/\s+/)
      .slice(5)
      .join(" ");
    form?.setValue(
      source,
      suffix === "" ? suggestion.crontab : `${suggestion.crontab} ${suffix}`,
      { shouldDirty: true, shouldTouch: true, shouldValidate: true },
    );
  };

  const unknown = translate("schedulePreview.unknown");

  return (
    <SimpleCard
      title={translate("schedulePreview.title")}
      subheader={translate("schedulePreview.description")}
      footer={
        <Button
          variant="outlined"
          size="small"
          disabled={!previewable || loading}
          onClick={() => void ask()}
        >
          {loading
            ? translate("schedulePreview.loading")
            : translate("schedulePreview.button")}
        </Button>
      }
    >
      <Stack spacing={1}>
        {!previewable && (
          <Typography variant="body2" color="text.secondary">
            {translate("schedulePreview.missingService")}
          </Typography>
        )}
        {error !== null && (
          <Alert severity="error">
            {translate("schedulePreview.error", { detail: error })}
          </Alert>
        )}
        {isStale && (
          <Alert severity="info">{translate("schedulePreview.stale")}</Alert>
        )}
        {answer !== null && (
          <>
            <Metric
              label={translate("schedulePreview.nextRuns")}
              value={
                answer.nextOccurrences.length === 0
                  ? unknown
                  : answer.nextOccurrences
                      .slice(0, SHOWN_OCCURRENCES)
                      .map(formatMoment)
                      .join(", ")
              }
            />
            <Metric
              label={translate("schedulePreview.interval")}
              value={
                answer.intervalSeconds === null
                  ? unknown
                  : formatSeconds(answer.intervalSeconds)
              }
            />
            <Metric
              label={translate("schedulePreview.p50")}
              value={
                answer.elapsed.p50Seconds === null
                  ? unknown
                  : formatSeconds(answer.elapsed.p50Seconds)
              }
            />
            <Metric
              label={translate("schedulePreview.p95")}
              value={
                answer.elapsed.p95Seconds === null
                  ? unknown
                  : formatSeconds(answer.elapsed.p95Seconds)
              }
            />
            <Metric
              label={translate("schedulePreview.samples")}
              value={answer.elapsed.sampleCount}
            />
            {answer.warnings.length > 0 && (
              <Stack spacing={0.5}>
                <Typography variant="body2" color="text.secondary">
                  {translate("schedulePreview.warnings")}
                </Typography>
                {answer.warnings.map((warning) => (
                  <Alert key={warning.code} severity="warning">
                    {warning.message}
                  </Alert>
                ))}
              </Stack>
            )}
            {(answer.suggestions ?? []).length > 0 && (
              <Stack spacing={0.5}>
                <Typography variant="body2" color="text.secondary">
                  {translate("schedulePreview.suggestions")}
                </Typography>
                {(answer.suggestions ?? []).map((suggestion) => (
                  <Alert
                    key={`${suggestion.crontab}@${suggestion.horizonDays}`}
                    severity="info"
                    action={
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={() => apply(suggestion)}
                      >
                        {translate("schedulePreview.suggestionApply")}:{" "}
                        <Typography component="span" variant="inherit">
                          {suggestion.crontab}
                        </Typography>
                      </Button>
                    }
                  >
                    <Stack spacing={0.25}>
                      <Metric
                        label={translate(
                          "schedulePreview.suggestionFirings",
                        )}
                        value={`${suggestion.firingCount} / ${suggestion.horizonDays} d`}
                      />
                      <Metric
                        label={translate(
                          "schedulePreview.suggestionOccupancy",
                        )}
                        value={`${formatSeconds(suggestion.expectedWorkerSeconds)} / ${formatSeconds(suggestion.originalWorkerSeconds)}`}
                      />
                      <Metric
                        label={translate(
                          "schedulePreview.suggestionSamples",
                        )}
                        value={
                          <>{`${suggestion.sampleCount} (${suggestion.queue})`}</>
                        }
                      />
                      <Typography variant="caption">
                        {suggestion.reason}
                      </Typography>
                    </Stack>
                  </Alert>
                ))}
              </Stack>
            )}
            {answer.suggestions.length === 0 &&
              answer.suggestionsReason !== null && (
                <Typography variant="caption" color="text.secondary">
                  {translate("schedulePreview.noSuggestions")}:{" "}
                  <Typography component="span" variant="inherit" color="inherit">
                    {answer.suggestionsReason}
                  </Typography>
                </Typography>
              )}
            {answer.capacity === null && (
              <Typography variant="caption" color="text.secondary">
                {translate("schedulePreview.capacity")}:{" "}
                {answer.capacityReason}
              </Typography>
            )}
          </>
        )}
      </Stack>
    </SimpleCard>
  );
};

export default SchedulePreviewPanel;
