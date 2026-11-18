/**
 * The bounded ISO 8601 grammar of the OWS time dimension.
 *
 * A WMS time dimension advertises its observations as instants and the step between them as a
 * duration, both within the shapes of ISO 8601 the profile allows. Reading them needs no calendar
 * library: an instant is a calendar date with a time of day and an offset, which the platform's own
 * `Date` answers exactly once the shape has been checked, and a duration is a handful of amounts
 * bound to their units.
 *
 * The grammar is deliberately bounded. What a service advertises outside these shapes is answered by
 * nothing, which the caller reads as "not an interval I can step through" — the honest answer of a
 * viewer which will not guess at a time it cannot name back to the service.
 *
 * Two readings are worth naming, because each is a reason to check the shape instead of handing the
 * text to `Date.parse`:
 * - a time without an offset is read as UTC. The dimension is advertised with the units ISO8601 and
 *   the request carries its TIME in UTC, so the wall clock a `datetime-local` input answers belongs
 *   to the service; `Date.parse` would read it as the wall clock of the *viewer* and move every
 *   observation of the range by the difference.
 * - a second of 60 is a leap second, which no `Date` holds. It names the moment at which the minute
 *   before its successor ends, so the arithmetic answers the following minute.
 */

/** the milliseconds of a second, a minute, an hour and a day */
const MS_PER_SECOND = 1000;
const MS_PER_MINUTE = 60 * MS_PER_SECOND;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;
const MS_PER_DAY = 24 * MS_PER_HOUR;

/** the number of days every month of a common year has, by its 0-based index */
const DAYS_OF_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * An instant of the WMS profile: the calendar date in its extended form, the time of day behind a
 * `T` or a space down to the minute with optional seconds and fraction, and an optional offset of
 * hours, or of hours and minutes with or without their colon.
 */
const INSTANT_PATTERN = new RegExp(
    String.raw`^(\d{4})-(\d{2})-(\d{2})`
    + String.raw`(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?`
    + String.raw`(Z|[+-]\d{2}(?::?\d{2})?)?$`,
    'i');

/** an amount of a duration: digits with an optional fraction, the only shape a WMS duration states */
const AMOUNT = String.raw`\d+(?:\.\d+)?`;

/**
 * A duration: `P`, at least one further character, the date units in their fixed order and
 * optionally `T` with the time units in theirs. The amounts carry no sign, because a step says how
 * far the next observation lies and never backwards.
 */
const DURATION_PATTERN = new RegExp(
    `^P(?=.+)(?:(${AMOUNT})Y)?(?:(${AMOUNT})M)?(?:(${AMOUNT})W)?(?:(${AMOUNT})D)?`
    + `(?:T(?=.+)(?:(${AMOUNT})H)?(?:(${AMOUNT})M)?(?:(${AMOUNT})S)?)?$`);

/** whether the given year has a 29th of February */
const isLeapYear = (year: number): boolean => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

/** the number of days the given 0-based month of the given year has */
const daysInMonth = (year: number, month: number): number =>
    month === 1 && isLeapYear(year) ? 29 : DAYS_OF_MONTH[month];

/**
 * The milliseconds of midnight at the start of the given UTC calendar day, or nothing when the month
 * has no such day. `Date.UTC` counts on from the last day it has instead of refusing the 30th of
 * February, so the fields are read back; the year goes through `setUTCFullYear` which, unlike
 * `Date.UTC`, does not map a year below 100 into the twentieth century.
 */
const utcDay = (year: number, month: number, day: number): number | undefined => {
    const date = new Date(Date.UTC(2000, 0, 1));
    date.setUTCFullYear(year, month, day);
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month || date.getUTCDate() !== day)
        return undefined;
    return date.getTime();
};

/** the moment a time zone suffix moves the wall clock by, `Z` naming none */
const offsetMilliseconds = (offset: string): number | undefined => {
    if (offset.toUpperCase() === 'Z') return 0;
    const digits = offset.slice(1).replace(':', '');
    const hours = Number(digits.slice(0, 2));
    const minutes = digits.length > 2 ? Number(digits.slice(2)) : 0;
    if (hours > 23 || minutes > 59) return undefined;
    return (offset[0] === '-' ? -1 : 1) * (hours * MS_PER_HOUR + minutes * MS_PER_MINUTE);
};

/**
 * The instant an ISO 8601 time names, as the milliseconds since the epoch, or nothing when the text
 * names no instant of the grammar above. A time without an offset is UTC, and a fraction shorter than
 * a millisecond is read down to it, which is all a `Date` can hold.
 */
export const parseInstant = (value: string): number | undefined => {
    const parts = INSTANT_PATTERN.exec(value);
    if (parts === null) return undefined;
    const hour = parts[4] === undefined ? 0 : Number(parts[4]);
    const minute = parts[5] === undefined ? 0 : Number(parts[5]);
    // a second of 60 is a leap second: the arithmetic of the following minute is its moment
    const second = parts[6] === undefined ? 0 : Number(parts[6]);
    const millisecond = parts[7] === undefined ? 0 : Number(parts[7].slice(0, 3).padEnd(3, '0'));
    const offset = parts[8] === undefined ? 0 : offsetMilliseconds(parts[8]);
    const day = utcDay(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
    if (offset === undefined || day === undefined) return undefined;
    if (hour > 23 || minute > 59 || second > 60) return undefined;
    return day + hour * MS_PER_HOUR + minute * MS_PER_MINUTE + second * MS_PER_SECOND + millisecond - offset;
};

/** whether the text names an instant, which is all a value list of a time dimension is asked */
export const isInstant = (value: string): boolean => parseInstant(value) !== undefined;

/** the instant as the canonical UTC text, the shape a WMS request carries its TIME in */
export const formatInstant = (instant: number): string => new Date(instant).toISOString();

/**
 * An ISO 8601 duration as the two amounts a viewer steps by: whole calendar months, which have no
 * length in milliseconds, and the length of everything else.
 */
export type IsoDuration = {
    months: number
    ms: number
}

/**
 * The duration a time dimension advertises as its step, or nothing when the text names no duration
 * of the grammar above. A year and a month are counted as months, so a fractional year is a duration
 * as long as it resolves to whole months: a month is the finest calendar unit an observation of a
 * range can be stepped by, so nothing does for the rest.
 */
export const parseDuration = (value: string): IsoDuration | undefined => {
    const parts = DURATION_PATTERN.exec(value);
    if (parts === null) return undefined;
    const amount = (index: number) => parts[index] === undefined ? 0 : Number(parts[index]);
    const months = amount(1) * 12 + amount(2);
    if (!Number.isInteger(months)) return undefined;
    const ms = amount(3) * 7 * MS_PER_DAY + amount(4) * MS_PER_DAY
        + amount(5) * MS_PER_HOUR + amount(6) * MS_PER_MINUTE + amount(7) * MS_PER_SECOND;
    return { months, ms };
};

/** whether the duration moves an observation on at all, which a step of `P0D` does not */
export const isPositiveDuration = (duration: IsoDuration): boolean => duration.months > 0 || duration.ms > 0;

/**
 * The observation `index` steps of the given duration after the given instant.
 *
 * The calendar months are applied first and to the day of the month the start names: a monthly step
 * advertises the same day of every month, and where that day does not exist — the 31st of February —
 * the observation falls back to the last day the month has. The length is added behind that, because
 * it is the same length for every observation and must not be moved by a clamp.
 */
export const stepInstant = (start: number, step: IsoDuration, index: number): number => {
    const months = step.months * index;
    const length = step.ms * index;
    if (months === 0) return start + length;
    const total = new Date(start).getUTCFullYear() * 12 + new Date(start).getUTCMonth() + months;
    const year = Math.floor(total / 12);
    const month = total - year * 12;
    const date = new Date(start);
    date.setUTCFullYear(year, month, Math.min(date.getUTCDate(), daysInMonth(year, month)));
    return date.getTime() + length;
};
