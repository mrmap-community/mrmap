/**
 * The reading of a crontab expression, for a row which shows one (#1082).
 *
 * `CronInput` lets an administrator *set* a crontab by its five parts; nothing
 * in the frontend says what a set expression means. A row of `0 3 * * *` is
 * readable to whoever wrote it and meaningless to everyone else, so the rhythm
 * is named next to the expression.
 *
 * Only the shapes an administrator picks with `CronInput` are read: `CronInput`
 * answers lists of concrete numbers and `*`, and the step forms of a field which
 * the harvest of a catalogue is actually scheduled with. Anything else - a
 * range, a list combined with a step, an expression of another length - answers
 * no reading, because a wrong reading of a schedule is worse than none: the raw
 * expression stands on its own in the row either way.
 */
/** the sentence which names the rhythm, as a key below `cronReading` */
export type CronRhythm =
  | "everyMinute"
  | "everyNMinutes"
  | "everyNHours"
  | "hourly"
  | "daily"
  | "weekly"
  | "monthly"
  | "yearly";

export interface CronReading {
  /** the key of the sentence which names the rhythm */
  key: CronRhythm;
  /** the minute of the hour as "07:05", for the rhythms which name one */
  time?: string;
  /** how many minutes or hours between two runs, for the step rhythms */
  every?: number;
  /** the minute of the hour, for the rhythm which fires once an hour */
  minute?: number;
  /** the weekdays by the numbers of the crontab, where 0 is the first */
  weekdays?: number[];
  /** the day of the month the expression names */
  dayOfMonth?: number;
  /** the month the expression names, 1 to 12 */
  month?: number;
}

const FIELD_COUNT = 5;

/** the concrete numbers of a field within the range that field has, or nothing */
const numbers = (
  field: string,
  minimum: number,
  maximum: number,
): number[] | undefined => {
  const values = field.split(",").map((part) => Number(part));
  if (
    field.length === 0 ||
    values.some(
      (value) =>
        !Number.isInteger(value) || value < minimum || value > maximum,
    )
  ) {
    return undefined;
  }
  return values;
};

/** the field of a crontab which lets everything through */
const isEvery = (field: string) => field === "*";

/** the step of a field, as in every ten minutes, or nothing if it is no step */
const step = (field: string): number | undefined => {
  const match = /^\*\/(\d+)$/.exec(field);
  return match === null ? undefined : Number(match[1]);
};

/** one concrete number of a field, or nothing for `*`, a list or a step */
const single = (
  field: string,
  minimum: number,
  maximum: number,
): number | undefined => {
  const values = numbers(field, minimum, maximum);
  return values?.length === 1 ? values[0] : undefined;
};

const timeOfDay = (minute: number, hour: number) =>
  `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

/** the ranges of the five fields of a crontab */
const MINUTE = [0, 59] as const;
const HOUR = [0, 23] as const;
const DAY_OF_MONTH = [1, 31] as const;
const MONTH = [1, 12] as const;
const WEEKDAY = [0, 6] as const;

/**
 * The rhythm a crontab expression schedules, or nothing for an expression this
 * reading does not know.
 *
 * @param expression the crontab as the api answers it
 */
export const readCron = (
  expression?: string | null,
): CronReading | undefined => {
  const fields = (expression ?? "").trim().split(/\s+/);
  if (fields.length !== FIELD_COUNT) return undefined;
  const [minute, hour, dayOfMonth, month, weekday] = fields;
  const rest = [dayOfMonth, month, weekday];
  const everyRest = rest.every(isEvery);

  if (isEvery(minute) && isEvery(hour) && everyRest) {
    return { key: "everyMinute" };
  }
  const minuteStep = step(minute);
  if (
    minuteStep !== undefined &&
    minuteStep <= MINUTE[1] &&
    isEvery(hour) &&
    everyRest
  ) {
    return { key: "everyNMinutes", every: minuteStep };
  }
  const hourStep = step(hour);
  const minuteOfStep = single(minute, ...MINUTE);
  if (
    hourStep !== undefined &&
    hourStep <= HOUR[1] &&
    minuteOfStep !== undefined &&
    everyRest
  ) {
    return {
      key: "everyNHours",
      every: hourStep,
      minute: minuteOfStep,
    };
  }
  const minuteOfHour = single(minute, ...MINUTE);
  if (minuteOfHour !== undefined && isEvery(hour) && everyRest) {
    return { key: "hourly", minute: minuteOfHour };
  }
  const hourOfDay = single(hour, ...HOUR);
  if (minuteOfHour === undefined || hourOfDay === undefined) return undefined;
  const time = timeOfDay(minuteOfHour, hourOfDay);

  if (everyRest) return { key: "daily", time };
  const weekdays = numbers(weekday, ...WEEKDAY);
  if (isEvery(dayOfMonth) && isEvery(month) && weekdays !== undefined) {
    return { key: "weekly", weekdays, time };
  }
  const day = single(dayOfMonth, ...DAY_OF_MONTH);
  if (day === undefined || !isEvery(weekday)) return undefined;
  const monthOfYear = single(month, ...MONTH);
  if (isEvery(month)) return { key: "monthly", dayOfMonth: day, time };
  if (monthOfYear !== undefined) {
    return { key: "yearly", dayOfMonth: day, month: monthOfYear, time };
  }
  return undefined;
};

export default readCron;
