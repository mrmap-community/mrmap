import { useMemo } from "react";
import {
  type RaRecord,
  useLocaleState,
  useRecordContext,
  useResourceDefinition,
  useTranslate,
  WrapperField,
} from "react-admin";
import { ReadyState } from "react-use-websocket";

import {
  Chip,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";

import { useHttpClientContext } from "../../../context/HttpClientContext";
import ListGuesser, {
  type ListGuesserProps,
} from "../../../jsonapi/components/ListGuesser";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import ProgressField from "../../Field/ProgressField";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../Lists/CustomListActions";
import BulkStopHarvestingJobsButton from "./BulkStopHarvestingJobsButton";
import HarvestingPhaseStepper from "./HarvestingPhaseStepper";

/** the runs are answered newest end first, the way the screen is drawn */
const LIST_SORT: NonNullable<ListGuesserProps["sort"]> = {
  field: "doneAt",
  order: "DESC",
};

const PER_PAGE = 25;

/**
 * The attributes the rows of this screen read, as the api names them in a
 * sparse fieldset, and nothing else (#1037): the statistics of a run are
 * annotated only for the request which names them, so the screen which watches
 * a harvest never pays for a column it does not show. `service` is named for
 * the catalogue of the row, the harvesting switches and the step size for the
 * new harvest which an ended row offers.
 */
export const LIST_FIELDS = [
  "id",
  "service",
  "phase",
  "phase_label",
  "date_created",
  "done_at",
  "total_records",
  "done_steps",
  "total_steps",
  "progress",
  "records_per_minute",
  "max_step_size",
  "unhandled_records_count",
  "import_error_count",
  "harvest_datasets",
  "harvest_services",
];

/** the columns are fixed by the rows of this screen, so none of them is chosen */
const FixedListActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

const useNumberFormat = () => {
  const [locale] = useLocaleState();
  return useMemo(
    () => new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-GB"),
    [locale],
  );
};

const useDateTimeFormat = () => {
  const [locale] = useLocaleState();
  return useMemo(
    () =>
      new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
    [locale],
  );
};

/** the runtime of a run in the shape the screen of a run already gives it */
const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds / 60) % 60;
  return [
    ...(hours ? [`${hours} h`] : []),
    ...(hours || minutes ? [`${minutes} min`] : []),
    `${seconds % 60} s`,
  ].join(" ");
};

const elapsedSeconds = (from?: string | null, to?: string | null) => {
  if (!from) return undefined;
  const end = to ? new Date(to).getTime() : Date.now();
  return Math.max(0, Math.floor((end - new Date(from).getTime()) / 1000));
};

/**
 * The catalogue of the run with the run beneath it: the catalogue is what tells
 * the rows of one deployment apart, while a run has no title of its own (#1045).
 */
const RunCatalogue = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const format = useNumberFormat();
  if (!record) return null;
  return (
    <Stack spacing={0.25} sx={{ minWidth: 150 }}>
      <JsonApiReferenceField
        source="service"
        reference="CatalogueService"
        sx={{ fontWeight: 600 }}
      />
      <Typography variant="caption" color="text.secondary">
        {translate("harvestRun.list.runCaption", { id: record.id })}
        {" · "}
        {record.maxStepSize != null
          ? translate("harvestRun.list.stepSizeCaption", {
              size: format.format(record.maxStepSize),
            })
          : translate("harvestRun.list.stepSizeUnknown")}
      </Typography>
    </Stack>
  );
};

/** the phases of a run which ended, as the api numbers them */
const COMPLETED_PHASE = 4;
const ABORTED_PHASE = 5;
const COUNTING_PHASE = 1;
const QUEUED_PHASE = 0;

const phaseColor = (phase: number) => {
  if (phase === COMPLETED_PHASE) return "success";
  if (phase === ABORTED_PHASE) return "warning";
  return "info";
};

/** the phase the api names, above the three stages the run works through */
const RunPhase = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  if (!record) return null;
  return (
    <Stack spacing={0.5} sx={{ minWidth: 180 }}>
      <Chip
        size="small"
        color={phaseColor(record.phase)}
        label={record.phaseLabel}
        sx={{ width: "fit-content", height: "auto", py: 0.5 }}
      />
      <HarvestingPhaseStepper phase={record.phase} sx={{ my: 0 }} />
      {record.phase === QUEUED_PHASE && (
        <Tooltip title={translate("harvestRun.list.queuedTooltip")}>
          <Typography variant="caption" color="text.secondary">
            {translate("harvestRun.list.queued")}
          </Typography>
        </Tooltip>
      )}
    </Stack>
  );
};

const progressColor = (record: RaRecord) => phaseColor(record.phase);

/**
 * How far the run is in its own work. A run whose total is not known yet is
 * drawn as a bar which tells no share and is captioned as such: it has measured
 * nothing and answers no percentage either.
 */
const RunProgress = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const format = useNumberFormat();
  if (!record) return null;
  const withoutTotal = !record.doneAt && record.totalRecords == null;
  const caption = () => {
    if (withoutTotal) return translate("harvestRun.list.totalUnknown");
    if (record.totalSteps != null && record.doneSteps != null) {
      return translate("harvestRun.list.stepsCaption", {
        done: format.format(record.doneSteps),
        total: format.format(record.totalSteps),
      });
    }
    return translate("harvestRun.list.noEstimate");
  };
  return (
    <Stack spacing={0.5} sx={{ minWidth: 140 }}>
      {withoutTotal ? (
        <LinearProgress
          variant="indeterminate"
          aria-label={translate("harvestingActivity.progress")}
        />
      ) : (
        <ProgressField source="progress" getColor={progressColor} />
      )}
      <Typography variant="caption" color="text.secondary">
        {caption()}
      </Typography>
    </Stack>
  );
};

/**
 * What a run stores per minute. Only a run which ended measured a whole
 * harvest, so a run which is still working answers none (#692) and the row says
 * that instead of drawing a number it does not have.
 */
const RunThroughput = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const format = useNumberFormat();
  if (!record) return null;
  return (
    <Tooltip title={translate("harvestRun.list.throughputTooltip")}>
      <Stack spacing={0.25} sx={{ minWidth: 120 }}>
        {record.recordsPerMinute != null ? (
          <>
            <Typography>
              {translate("harvestRun.list.throughputValue", {
                count: format.format(Math.round(record.recordsPerMinute)),
              })}
            </Typography>
            {record.maxStepSize != null && (
              <Typography variant="caption" color="text.secondary">
                {translate("harvestRun.list.throughputCaption", {
                  size: format.format(record.maxStepSize),
                })}
              </Typography>
            )}
          </>
        ) : (
          <>
            <Typography>—</Typography>
            <Typography variant="caption" color="text.secondary">
              {translate("harvestRun.list.noThroughput")}
            </Typography>
          </>
        )}
      </Stack>
    </Tooltip>
  );
};

/**
 * One column for both questions: how long a run which works has already run,
 * and how long one which ended took. The moment a run was made is recorded only
 * for some runs (#1079), and the time left of a running run is #1071 - until
 * that answers, a running row says that nothing is estimated.
 */
const RunTime = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const format = useDateTimeFormat();
  if (!record) return null;
  const seconds = elapsedSeconds(record.dateCreated, record.doneAt);
  const duration = seconds != null ? formatDuration(seconds) : null;
  const notRecorded = translate("harvestRun.notRecorded");
  const tooltip = () => {
    if (!record.dateCreated) return translate("harvestRun.list.createdUnknown");
    if (record.doneAt) {
      return translate("harvestRun.list.endedTimeTooltip", {
        created: format.format(new Date(record.dateCreated)),
        finished: format.format(new Date(record.doneAt)),
      });
    }
    return translate("harvestRun.list.elapsedTooltip", {
      created: format.format(new Date(record.dateCreated)),
      elapsed: duration ?? notRecorded,
    });
  };
  const caption = () => {
    if (record.doneAt) {
      return translate("harvestRun.list.endedCaption", {
        at: format.format(new Date(record.doneAt)),
      });
    }
    if (record.totalRecords == null) {
      return translate("harvestRun.list.noEstimateTotal");
    }
    return translate("harvestRun.list.noEstimate");
  };
  return (
    <Tooltip title={tooltip()}>
      <Stack spacing={0.25} sx={{ minWidth: 120 }}>
        <Typography>{duration ?? notRecorded}</Typography>
        <Typography variant="caption" color="text.secondary">
          {caption()}
        </Typography>
      </Stack>
    </Tooltip>
  );
};

/**
 * The records this run was told to bring, with what still waits for its import
 * and what refused it. The count belongs to the run and is not the number of
 * records the MrMap catalogue holds.
 */
const RunRecords = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const format = useNumberFormat();
  if (!record) return null;
  const label = () => {
    if (record.totalRecords != null) {
      return translate("harvestRun.list.recordsValue", {
        smart_count: record.totalRecords,
        count: format.format(record.totalRecords),
      });
    }
    if (record.phase === COUNTING_PHASE) {
      return translate("harvestRun.list.recordsUnknown");
    }
    return translate("harvestRun.list.totalUnknown");
  };
  return (
    <Tooltip title={translate("harvestRun.list.recordsTooltip")}>
      <Stack spacing={0.5} sx={{ minWidth: 130 }}>
        <Typography>{label()}</Typography>
        {!!record.unhandledRecordsCount && (
          <Chip
            size="small"
            color="warning"
            label={translate("harvestRun.list.awaitingChip", {
              smart_count: record.unhandledRecordsCount,
              count: format.format(record.unhandledRecordsCount),
            })}
            sx={{ width: "fit-content", height: "auto", py: 0.5 }}
          />
        )}
        {!!record.importErrorCount && (
          <Chip
            size="small"
            color="error"
            label={translate("harvestRun.list.importErrorChip", {
              smart_count: record.importErrorCount,
              count: format.format(record.importErrorCount),
            })}
            sx={{ width: "fit-content", height: "auto", py: 0.5 }}
          />
        )}
      </Stack>
    </Tooltip>
  );
};

/** what this screen answers, so that a missing column is not a missing helper */
const ListNote = () => {
  const translate = useTranslate();
  return (
    <Stack spacing={0.25} sx={{ px: 1 }}>
      <Typography variant="body2" color="text.secondary">
        {translate("harvestRun.list.listDescription")}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {translate("harvestRun.list.selectUnfinished")}
      </Typography>
    </Stack>
  );
};

/**
 * The columns of the screen, declared here instead of guessed from the schema:
 * a column of a run answers what the run is doing, how far it is and what it
 * has brought, and the sort follows the end of a run because the harvesting
 * records no creation date for the runs it makes itself (#1079).
 */
export const RUN_COLUMNS = [
  <WrapperField
    key="service"
    source="service"
    label="harvestRun.list.runHeading"
    sortable={false}
  >
    <RunCatalogue />
  </WrapperField>,
  <WrapperField
    key="phase"
    source="phase"
    label="harvestRun.list.phaseHeading"
    sortable={false}
  >
    <RunPhase />
  </WrapperField>,
  <WrapperField
    key="progress"
    source="progress"
    label="harvestRun.list.progressHeading"
    sortable={false}
  >
    <RunProgress />
  </WrapperField>,
  <WrapperField
    key="recordsPerMinute"
    source="recordsPerMinute"
    label="harvestRun.list.throughputHeading"
    sortable={false}
  >
    <RunThroughput />
  </WrapperField>,
  <WrapperField key="doneAt" source="doneAt" label="harvestRun.list.timeHeading">
    <RunTime />
  </WrapperField>,
  <WrapperField
    key="totalRecords"
    source="totalRecords"
    label="harvestRun.list.recordsHeading"
    sortable={false}
  >
    <RunRecords />
  </WrapperField>,
];

/**
 * The screen of the harvesting runs of every catalogue the caller may see.
 *
 * It is modelled on the screen of the registered services: the columns are
 * declared here instead of guessed from the schema, the column chooser is
 * switched off, and the sparse fieldset names exactly the attributes the rows
 * read. It is live the way the background-activity list is - the websocket
 * carries every change a run writes and an interval covers the time it is not
 * connected.
 *
 * A row of a run which did not end stops that run and only such a row is
 * selectable, because a run which ended has nothing left to stop. The facets,
 * the search and the tiles of the mockup are not here: the filterset of the
 * runs answers neither a phase, nor a time range, nor a catalogue title, so a
 * tile or a facet which no filter can answer would count a lie (#1080).
 */
const ListHarvestingJob = () => {
  const { hasEdit } = useResourceDefinition({ resource: "HarvestingJob" });
  // the bus reports every change of a run, the interval is only the fallback
  // while it is not connected
  const { realtimeIsReady } = useHttpClientContext();

  const queryOptions = useMemo(
    () => ({
      meta: {
        jsonApiParams: {
          "fields[HarvestingJob]": LIST_FIELDS.join(","),
        },
      },
    }),
    [],
  );

  return (
    <ListGuesser
      resource="HarvestingJob"
      realtime={true}
      columns={RUN_COLUMNS}
      header={<ListNote />}
      perPage={PER_PAGE}
      sort={LIST_SORT}
      refetchInterval={realtimeIsReady === ReadyState.OPEN ? false : 5000}
      queryOptions={queryOptions}
      ActionsComponent={FixedListActions}
      dataGridProps={{
        bulkActionButtons: <BulkStopHarvestingJobsButton />,
        isRowSelectable: (record: RaRecord) => !!hasEdit && !record.doneAt,
        sx: {
          "& .RaDatagrid-tableWrapper": { maxWidth: "100%", overflowX: "auto" },
          "& .RaDatagrid-table": { minWidth: 1000 },
          "& .RaDatagrid-headerCell": { whiteSpace: "nowrap" },
          "& .RaDatagrid-rowCell": { verticalAlign: "top" },
          "& .RaDatagrid-rowCell:last-child": { whiteSpace: "nowrap" },
          "& .RaDatagrid-rowCell:last-child .MuiButton-root": {
            fontSize: 0,
            minWidth: 32,
            p: 0.75,
          },
          "& .RaDatagrid-rowCell:last-child .MuiButton-startIcon": { m: 0 },
        },
      }}
    />
  );
};

export default ListHarvestingJob;
