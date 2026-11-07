import { Fragment, type ReactNode } from "react";
import {
  Chip,
  FunctionField,
  TextField,
  useLocaleState,
  useRecordContext,
  useTranslate,
} from "react-admin";

import { Stack, Typography } from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import RelativeDateField from "../../Field/RelativeDateField";
import EmptyList from "../../Lists/Empty";
import readCron from "./cronReading";
import ScheduleAttentionCounts from "./ScheduleAttentionCounts";
import ScheduleRowActions from "./ScheduleRowActions";

/**
 * The columns of the rows, in the order the screen shows them.
 *
 * The sparse fieldset of the resource in `Definition.tsx` names these too: the
 * request which answers a page goes out before the grid registered its columns,
 * and the next run of a schedule is only calculated for a request which asks for
 * it (#1082).
 */
export const SCHEDULE_LIST_FIELDS = [
  "id",
  "service",
  "enabled",
  "scheduling",
  "last_run_at",
  "next_run_at",
  "total_run_count",
];

/** the weekday of a crontab number, by the name the locale gives it */
const weekdayName = (index: number, locale?: string) =>
  new Intl.DateTimeFormat(locale, { weekday: "short" }).format(
    // the fourth of January 2026 is a Sunday, which is the first day of a crontab
    new Date(2026, 0, 4 + index),
  );

/** the month of a crontab number, by the name the locale gives it */
const monthName = (month: number, locale?: string) =>
  new Intl.DateTimeFormat(locale, { month: "short" }).format(
    new Date(2026, month - 1, 1),
  );

/**
 * The crontab of a schedule and what it says in words (#1082).
 *
 * The expression is the answer of the api and the thing an administrator edits,
 * so it stays the primary line; the reading of it is the second line, and only
 * for the rhythms `readCron` knows.
 */
const SchedulingCell = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const reading = readCron(record?.scheduling);
  const values: Record<string, string | number> = {
    expression: record?.scheduling ?? "",
  };
  if (reading?.time !== undefined) values.time = reading.time;
  if (reading?.every !== undefined) values.every = reading.every;
  if (reading?.minute !== undefined) values.minute = reading.minute;
  if (reading?.weekdays !== undefined) {
    values.days = reading.weekdays
      .map((day) => weekdayName(day, locale))
      .join(", ");
  }
  if (reading?.dayOfMonth !== undefined) values.day = reading.dayOfMonth;
  if (reading?.month !== undefined) values.month = monthName(reading.month, locale);
  return (
    <Stack spacing={0.25}>
      <span>{record?.scheduling}</span>
      {reading !== undefined && (
        <Typography variant="body2" color="text.secondary">
          {translate(`cronReading.${reading.key}`, values)}
        </Typography>
      )}
    </Stack>
  );
};

/** the flag of a schedule, which is the state every row of the screen shows */
const EnabledCell = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Chip
      size="small"
      variant="outlined"
      color={record?.enabled ? "success" : "default"}
      label={translate(
        record?.enabled ? "harvestingSchedules.enabled" : "harvestingSchedules.disabled",
      )}
    />
  );
};

const ListPeriodicHarvestingJob = (): ReactNode => {
  const record = useRecordContext();
  const translate = useTranslate();
  // the same screen is the tab of one catalogue: the record of that catalogue
  // scopes the rows, the global screen of the menu answers all of them (#1080)
  const relatedProps =
    record !== undefined
      ? {
          resource: "PeriodicHarvestingJob",
          relatedResource: { resource: "CatalogueService", id: record.id },
        }
      : {};
  return (
    <ListGuesser
      header={<ScheduleAttentionCounts />}
      resource="PeriodicHarvestingJob"
      sort={{ field: "nextRunAt", order: "ASC" }}
      perPage={25}
      columns={[
        <JsonApiReferenceField
          key="service"
          source="service"
          reference="CatalogueService"
          sortable={false}
          label="resources.PeriodicHarvestingJob.fields.service"
        />,
        <FunctionField
          key="enabled"
          source="enabled"
          label="resources.PeriodicHarvestingJob.fields.enabled"
          render={() => <EnabledCell />}
        />,
        <FunctionField
          key="scheduling"
          source="scheduling"
          sortable={false}
          label="resources.PeriodicHarvestingJob.fields.scheduling"
          render={() => <SchedulingCell />}
        />,
        <FunctionField
          key="lastRunAt"
          source="lastRunAt"
          label="resources.PeriodicHarvestingJob.fields.lastRunAt"
          render={(record) => (
            <RelativeDateField
              source="lastRunAt"
              record={record}
              emptyText={translate("harvestingSchedules.neverRan")}
            />
          )}
        />,
        <FunctionField
          key="nextRunAt"
          source="nextRunAt"
          label="resources.PeriodicHarvestingJob.fields.nextRunAt"
          render={(record) => (
            <RelativeDateField
              source="nextRunAt"
              record={record}
              emptyText={translate("harvestingSchedules.noNextRun")}
            />
          )}
        />,
        <TextField
          key="totalRunCount"
          source="totalRunCount"
          sortable={false}
          label="resources.PeriodicHarvestingJob.fields.totalRunCount"
        />,
      ]}
      additionalActions={
        <Fragment>
          <ScheduleRowActions />
        </Fragment>
      }
      empty={<EmptyList />}
      {...relatedProps}
    />
  );
};

export default ListPeriodicHarvestingJob;
