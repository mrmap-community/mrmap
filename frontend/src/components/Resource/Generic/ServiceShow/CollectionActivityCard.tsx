import {
  DateField,
  Link,
  Loading,
  useCreatePath,
  useGetList,
  useRecordContext,
  useTranslate,
  RecordContextProvider,
  type RaRecord,
} from "react-admin";

import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  Chip,
  Grid,
  Stack,
  Typography,
} from "@mui/material";

import ProgressField from "../../../Field/ProgressField";
import SimpleCard from "../../../MUI/SimpleCard";
import {
  hasProgressTotal,
  isActive,
  isTerminal,
  jobStateOf,
  type BackgroundJobRecord,
} from "../../BackgroundProcess/JobCenter/jobStore";
import ProcessStatusField from "../../BackgroundProcess/ProcessStatusField";

/** the process type the registration of a service reports as (`notify/enums.py`) */
const REGISTRATION = "registering";

/** The work states a retained reference keeps (#1263): the row of a reference
 *  whose document was stored is deleted, so its absence is the success and no
 *  state names it; what stays is what waits, what is being worked and what
 *  failed. */
const REFERENCE_PENDING = 0;
const REFERENCE_LEASED = 1;
const REFERENCE_FAILED = 2;

/** how many registration processes the card follows: a service is registered
 *  once and re-registered by an update (#1274), so three answer "this one and
 *  the ones before it" without paging a job list on the service page */
const SHOWN_PROCESSES = 3;

/** how many retained references of those processes the card reads. One bounded
 *  request answers both questions the card still has - whether the caller may
 *  read the per-reference list at all and which elements its references
 *  describe - because nothing on the card is counted while it is read (#1037).
 *  The per-reference screen of #1265 owns the paging. */
const SHOWN_REFERENCES = 25;

/** the elements named under one process; the rest is what the references link
 *  of that process shows */
const SHOWN_ELEMENTS = 8;

/** the harvesting activity card of a catalogue watches its runs with this
 *  interval; a registration which decided stops being watched (#1078) */
const POLL_MILLISECONDS = 5000;

/** every number the card renders is one of these stored fields: the plan is
 *  written when the collection seals it, every outcome moves its counter and
 *  the remainder is closed as skipped when the run decides (#1259, #1263).
 *  The card computes nothing, so it needs no annotation and no statistics. */
const PROCESS_FIELDS = [
  "id",
  "status",
  "state",
  "process_type",
  "phase",
  "progress",
  "date_created",
  "done_at",
  "total_steps",
  "done_steps",
  "error_summary",
  "references_total",
  "references_stored",
  "references_failed",
  "references_skipped",
].join(",");

/** the element a retained reference describes, named by the one relation which
 *  is set - the same shape by which `MetadataRelation` says what it relates */
const DESCRIBED_BY_SOURCE = [
  { source: "describedLayer", resource: "Layer" },
  { source: "describedFeaturetype", resource: "FeatureType" },
  { source: "describedWms", resource: "WebMapService" },
  { source: "describedWfs", resource: "WebFeatureService" },
];

/** The outcomes the collection stores on the process, in the order the run
 *  decided them. The labels are the api's own labels of these counters
 *  (`notify/serializers.py`) in the words #1267 agreed for collecting.
 *  `filter` is the lookup of the per-reference list which answers the outcome
 *  - the stored one has none, because a stored reference leaves no row behind
 *  (#1263), and a skipped reference only became skipped when the run decided,
 *  which is why both links are offered for a decided run only. */
const OUTCOMES: {
  key: string;
  source: string;
  filter?: (processId: RaRecord["id"]) => Record<string, string>;
}[] = [
  { key: "planned", source: "referencesTotal" },
  { key: "stored", source: "referencesStored" },
  {
    key: "failed",
    source: "referencesFailed",
    filter: (processId) => ({
      backgroundProcess: String(processId),
      state: String(REFERENCE_FAILED),
    }),
  },
  {
    key: "skipped",
    source: "referencesSkipped",
    filter: (processId) => ({
      backgroundProcess: String(processId),
      "state.in": `${REFERENCE_PENDING},${REFERENCE_LEASED}`,
    }),
  },
];

/** whether an api error says the caller may not read what was asked for; the
 *  same rule by which the run screen of a harvest decides about its log tab
 *  (#1083) */
const isForbidden = (error: unknown): boolean => {
  const e = error as { status?: number; response?: { status?: number } };
  return e?.status === 403 || e?.response?.status === 403;
};

/** the list of the references of one process, asked for by the lookups #1263
 *  declares for exactly this card on the temporary files endpoint */
const referencesPath = (filter: Record<string, string>): string =>
  `/TemporaryMdMetadataFile/list?filter=${encodeURIComponent(
    JSON.stringify(filter),
  )}`;

/** the elements the retained references of one process describe, newest plan
 *  first and every element once; a row which names no element - a document the
 *  planning could not attach - answers nothing */
const describedElements = (
  rows: RaRecord[],
  processId: RaRecord["id"],
  createPath: ReturnType<typeof useCreatePath>,
): { key: string; name: string; to: string }[] => {
  const elements = new Map<string, { key: string; name: string; to: string }>();
  rows
    .filter((row) => String(row?.backgroundProcess?.id) === String(processId))
    .forEach((row) => {
      const described = DESCRIBED_BY_SOURCE.find(
        ({ source }) => row?.[source]?.id != null,
      );
      if (described === undefined) return;
      const id = String(row[described.source].id);
      const key = `${described.resource}/${id}`;
      if (elements.has(key)) return;
      elements.set(key, {
        key,
        // the name the element carried when the plan was written, which the row
        // keeps after the element itself is gone; the id stands where the
        // element came without a title
        name: row.describedDisplay || id,
        to: createPath({ resource: described.resource, id, type: "show" }),
      });
    });
  return [...elements.values()];
};

/** One registration process: what it is doing, what it collected and the links
 *  into the screens which answer the details. Its shape is the shape of a run
 *  row of the harvesting activity card of a catalogue - the state chip, the
 *  phase, the progress and the outcome counters in front of the links - so the
 *  two cards differ by their fields and not by their vocabulary. */
const CollectionRun = ({
  process,
  rows,
  linksAllowed,
}: {
  process: BackgroundJobRecord;
  rows: RaRecord[];
  linksAllowed: boolean;
}) => {
  const translate = useTranslate();
  const createPath = useCreatePath();
  const state = jobStateOf(process);
  const running = isActive(process);
  const decided = isTerminal(process);
  const isFailed = state === "failed" || state === "aborted";
  // the kind with the reported phase behind it, exactly as the row of the job
  // center reads it: the phase is a key of the background activity
  // translations and a value which is no key - an error a task reported -
  // stays readable as it was written (#1267)
  const kind = translate(
    `backgroundActivity.jobCenter.processTypes.${process.processType}`,
    { _: process.processType },
  );
  const phase =
    typeof process.phase === "string" && process.phase !== ""
      ? translate(`backgroundActivity.phases.${process.phase}`, {
          _: process.phase,
        })
      : undefined;
  const reason =
    isFailed && process.errorSummary
      ? process.errorSummary
      : phase === undefined
        ? kind
        : `${kind} · ${phase}`;
  const planned = process.referencesTotal;
  const outcomes = OUTCOMES.filter(
    (outcome) => process[outcome.source] != null,
  );
  const unresolved =
    Number(process.referencesFailed ?? 0) +
    Number(process.referencesSkipped ?? 0);
  const elements = describedElements(rows, process.id, createPath);
  const shownElements = elements.slice(0, SHOWN_ELEMENTS);
  return (
    <RecordContextProvider value={process}>
      <Box
        sx={{
          p: 2,
          border: 1,
          borderColor: isFailed
            ? "error.main"
            : running
              ? "info.main"
              : "divider",
          borderRadius: 1,
        }}
      >
        <Stack
          direction="row"
          sx={{ justifyContent: "space-between", alignItems: "center", gap: 1 }}
        >
          <Typography variant="subtitle2">
            {translate("backgroundActivity.process", {
              id: String(process.id),
            })}
          </Typography>
          {/* the state of #1207 in the words of the job center, not a reading
              of a celery state */}
          <ProcessStatusField source="state" />
        </Stack>
        <Typography
          variant="body2"
          color={isFailed ? "error.main" : "text.secondary"}
        >
          {reason}
        </Typography>
        {running && (
          <ProgressField
            source="progress"
            indeterminate={!hasProgressTotal(process)}
            aria-label={translate("backgroundActivity.progress")}
            sx={{ my: 1.5 }}
          />
        )}
        {hasProgressTotal(process) && (
          <Typography variant="caption" color="text.secondary">
            {translate("backgroundActivity.steps", {
              done: process.doneSteps ?? 0,
              total: process.totalSteps,
            })}
          </Typography>
        )}
        {planned == null ? (
          // no plan was ever sealed: while the run works it has not read its
          // references yet, and a decided run of this kind never collected any
          // - the honest counterpart of a registration whose references of this
          // kind were dropped (#1257). Neither answer claims a number.
          <Typography variant="body2" color="text.secondary">
            {translate(
              running
                ? "collectionActivity.notPlanned"
                : "collectionActivity.notCollected",
            )}
          </Typography>
        ) : planned === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {translate("collectionActivity.nothingReferenced")}
          </Typography>
        ) : (
          <Grid container spacing={2} sx={{ mt: 1 }}>
            {outcomes.map((outcome) => {
              const count = Number(process[outcome.source]);
              const filter =
                decided && linksAllowed && outcome.filter
                  ? outcome.filter(process.id)
                  : undefined;
              const content = (
                <>
                  <Typography variant="body2" color="text.secondary">
                    {translate(`collectionActivity.${outcome.key}`)}
                  </Typography>
                  <Typography
                    variant="h5"
                    color={
                      count > 0 &&
                      outcome.key !== "planned" &&
                      outcome.key !== "stored"
                        ? "warning.main"
                        : "text.primary"
                    }
                  >
                    {count}
                  </Typography>
                </>
              );
              return (
                <Grid key={outcome.key} size={{ xs: 6, md: 3 }}>
                  <Card variant="outlined">
                    {filter === undefined ? (
                      <Box sx={{ p: 2 }}>{content}</Box>
                    ) : (
                      <CardActionArea
                        component={Link}
                        to={referencesPath(filter)}
                        sx={{ p: 2 }}
                      >
                        {content}
                      </CardActionArea>
                    )}
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        )}
        {decided && unresolved > 0 && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {translate("collectionActivity.unresolved", { count: unresolved })}
          </Alert>
        )}
        {linksAllowed && shownElements.length > 0 && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {translate("collectionActivity.describes")}
            </Typography>
            <Stack
              direction="row"
              spacing={1}
              sx={{ flexWrap: "wrap", gap: 1, mt: 0.5 }}
            >
              {shownElements.map((element) => (
                <Chip
                  key={element.key}
                  size="small"
                  clickable
                  component={Link}
                  to={element.to}
                  label={element.name}
                />
              ))}
            </Stack>
            {elements.length > shownElements.length && (
              <Typography variant="caption" color="text.secondary">
                {translate("collectionActivity.describesMore", {
                  count: elements.length - shownElements.length,
                })}
              </Typography>
            )}
          </Box>
        )}
        <Stack
          direction="row"
          sx={{ mt: 1, justifyContent: "space-between", alignItems: "center" }}
        >
          <Typography variant="caption" color="text.secondary">
            {/* the word of the harvesting card: one word family for both paths
                which collect (#1267, D6) */}
            {translate("harvestingActivity.started")}:{" "}
            <DateField source="dateCreated" showTime emptyText="—" />
          </Typography>
          <Stack direction="row" spacing={1}>
            {linksAllowed && (
              <Button
                size="small"
                component={Link}
                to={referencesPath({ backgroundProcess: String(process.id) })}
                label="collectionActivity.viewReferences"
              />
            )}
            <Button
              size="small"
              component={Link}
              to={createPath({
                resource: "BackgroundProcess",
                id: process.id,
                type: "show",
              })}
              label="backgroundActivity.viewDetails"
            />
          </Stack>
        </Stack>
      </Box>
    </RecordContextProvider>
  );
};

/**
 * What the registration of this service collected.
 *
 * One card per retained registration process, on the page of the service it
 * registered - the counterpart of the harvesting activity card of a catalogue,
 * which answers the same question for the runs of a catalogue. It is a view
 * onto the state the process retains: the phase and the state of #1207, the
 * counters #1263 stores and the references whose rows are still there. A
 * process which the retention of #1208 purged took its reference rows and their
 * stored documents with it, so the card says that it has nothing retained
 * rather than that the run collected nothing.
 *
 * It asks two bounded requests and computes nothing: the processes of this
 * service and the references those processes still keep. Aggregation per read
 * is what #1037 measured at 5.85 s cold and 12.2 s worst while a large import
 * writes the same tables, which is why every number here was stored by the run
 * which knows it.
 */
const CollectionActivityCard = () => {
  const service = useRecordContext();
  const translate = useTranslate();
  const serviceId = service?.id;

  // the registrations of THIS service, newest first: `relatedId` addresses the
  // resource a process reports for, and a service is addressed by its uuid, so
  // no other resource answers the same id (`notify/managers.py:visible_for_user`)
  const processes = useGetList<BackgroundJobRecord>(
    "BackgroundProcess",
    {
      filter: { relatedId: serviceId, processType: REGISTRATION },
      sort: { field: "dateCreated", order: "DESC" },
      pagination: { page: 1, perPage: SHOWN_PROCESSES },
      meta: {
        jsonApiParams: { "fields[BackgroundProcess]": PROCESS_FIELDS },
      },
    },
    {
      enabled: serviceId != null,
      // the card follows the registration an editor is watching and stops
      // polling once nothing of this service runs any more
      refetchInterval: (query) =>
        (query.state.data?.data ?? []).some(isActive)
          ? POLL_MILLISECONDS
          : false,
    },
  );
  const runs = processes.data ?? [];

  // the references the shown registrations still keep: what waits, what is
  // being worked and what failed. The same request answers whether the caller
  // may read that list at all - a service editor who may see the service but
  // not these rows gets the counters without the links, not a broken request.
  const references = useGetList(
    "TemporaryMdMetadataFile",
    {
      filter: { "backgroundProcess.in": runs.map((run) => String(run.id)).join(",") },
      sort: { field: "requestId", order: "DESC" },
      pagination: { page: 1, perPage: SHOWN_REFERENCES },
      meta: {
        jsonApiParams: {
          "fields[TemporaryMdMetadataFile]": [
            "id",
            "background_process",
            "state",
            "described_display",
            "described_layer",
            "described_featuretype",
            "described_wms",
            "described_wfs",
          ].join(","),
        },
      },
    },
    { enabled: runs.length > 0, retry: false },
  );
  const rows = references.data ?? [];
  // only a denial is an answer to this question: while the probe is on its way
  // the links are no lie, and a failure which is not about permission leaves
  // them where they belong (#1083)
  const linksAllowed = !isForbidden(references.error);

  const content = () => {
    if (processes.isPending) return <Loading />;
    if (processes.error)
      return (
        <Alert severity={isForbidden(processes.error) ? "info" : "error"}>
          {translate(
            isForbidden(processes.error)
              ? "collectionActivity.unreadable"
              : "collectionActivity.loadError",
          )}
        </Alert>
      );
    if (runs.length === 0)
      return (
        <Typography color="text.secondary">
          {translate("collectionActivity.noHistory")}
        </Typography>
      );
    return (
      <Stack spacing={2}>
        {runs.map((run) => (
          <CollectionRun
            key={run.id}
            process={run}
            rows={rows}
            linksAllowed={linksAllowed}
          />
        ))}
      </Stack>
    );
  };

  if (service == null) return null;
  return (
    <SimpleCard
      title={translate("collectionActivity.title")}
      cardProps={{ variant: "outlined", sx: { width: "100%", minWidth: 0 } }}
    >
      {content()}
    </SimpleCard>
  );
};

export { CollectionRun };
export default CollectionActivityCard;
