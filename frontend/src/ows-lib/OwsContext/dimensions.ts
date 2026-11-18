import type { Offering, OfferingDimension } from './types';

import { formatInstant, isInstant, isPositiveDuration, parseDuration, parseInstant, stepInstant } from '../iso8601';

/**
 * WMS asks the request for an advertised dimension through a well known parameter:
 * Standard time/elevation use TIME/ELEVATION; custom dimensions use DIM_<name>.
 */
export const getDimensionParameter = (name: string): string => {
    const trimmed = name.trim();
    if (trimmed.toLowerCase() === 'elevation') return 'ELEVATION';
    if (trimmed.toLowerCase() === 'time') return 'TIME';
    return `DIM_${trimmed.replace(/^dim_/i, '').toUpperCase()}`;
};

export type AdvertisedValues =
    | { kind: 'list'; values: string[] }
    | { kind: 'range'; start: number; stop: number; step?: number }
    | { kind: 'time-range'; start: string; stop: string; step?: string };

/** the shape of a numeric interval: two or three plain numbers, start, stop and at most a step */
const isNumericRangeParts = (parts: string[]): boolean =>
    parts.length >= 2 && parts.length <= 3
    && parts.every(part => part.trim() !== '' && Number.isFinite(Number(part)));

/** whether the text steps an observation of a time range on */
const isStep = (value: string): boolean => {
    const step = parseDuration(value);
    return step !== undefined && isPositiveDuration(step);
};

/**
 * The shape of a temporal interval: two valid ISO 8601 instants in order and at most one step which
 * moves an observation on. A step the grammar cannot walk, a fractional month among them, is not an
 * interval but text a viewer has to show as it is.
 */
const isTimeRangeParts = (parts: string[]): boolean => {
    if (parts.length !== 2 && parts.length !== 3) return false;
    const start = parseInstant(parts[0]);
    const stop = parseInstant(parts[1]);
    if (start === undefined || stop === undefined || start > stop) return false;
    return parts.length === 2 || isStep(parts[2]);
};

/**
 * Read advertised numeric and ISO 8601 temporal intervals without expanding large ranges.
 */
export const parseAdvertisedValues = (values: string): AdvertisedValues => {
    const parts = values.split('/');
    if (isNumericRangeParts(parts)) {
        const start = Number(parts[0]);
        const stop = Number(parts[1]);
        const step = parts.length === 3 ? Number(parts[2]) : undefined;
        return { kind: 'range', start, stop, ...(step !== undefined && step > 0 ? { step } : {}) };
    }
    if (isTimeRangeParts(parts)) {
        return { kind: 'time-range', start: parts[0], stop: parts[1], ...(parts[2] && { step: parts[2] }) };
    }
    return { kind: 'list', values: values.split(',').map(value => value.trim()).filter(Boolean) };
};

/** whether the instant is one of the observations a stepped time range advertises:
 *  the index of the step is unknown, so it is probed by growing a bound
 *  exponentially and searching it binary */
const isAdvertisedInstant = (range: Extract<AdvertisedValues, { kind: 'time-range' }>, target: number): boolean => {
    const at = timeRangeInstantAt(range);
    if (at === undefined) return false;
    let low = 0, high = 1;
    while (at(high) < target && high < Number.MAX_SAFE_INTEGER / 2) high *= 2;
    while (low <= high) {
        const middle = Math.floor((low + high) / 2);
        const candidate = at(middle);
        if (candidate === target) return true;
        if (candidate < target) low = middle + 1;
        else high = middle - 1;
    }
    return false;
};

/** whether the number is one of the observations a numeric range advertises */
const isAdvertisedNumber = (range: Extract<AdvertisedValues, { kind: 'range' }>, numeric: number): boolean => {
    if (numeric < Math.min(range.start, range.stop) || numeric > Math.max(range.start, range.stop)) return false;
    if (range.step === undefined) return true;
    const position = (numeric - range.start) / range.step;
    return Math.abs(position - Math.round(position)) < 1e-9;
};

/** The empty value stands for the server default and is always allowed. */
export const isAllowedDimensionValue = (dimension: OfferingDimension, value: string): boolean => {
    if (value === '') return true;
    const advertised = parseAdvertisedValues(dimension.values);
    if (advertised.kind === 'list')
        return advertised.values.includes(value) || value === dimension.default;
    if (advertised.kind === 'time-range') {
        if (value === dimension.default || value === dimension.values) return true;
        const instant = parseInstant(value);
        const start = parseInstant(advertised.start);
        const stop = parseInstant(advertised.stop);
        if (instant === undefined || start === undefined || stop === undefined) return false;
        if (instant < start || instant > stop) return false;
        if (!advertised.step) return true;
        return isAdvertisedInstant(advertised, instant);
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return false;
    return isAdvertisedNumber(advertised, numeric);
};

/** Whether a request parameter name carries the WMS time dimension, in any written case and with or without the DIM_ prefix. */
export const isTimeParameter = (name: string): boolean =>
    /^(?:dim_)?time$/i.test(name);

/** Whether the service advertises this dimension as its time: the well known name or ISO 8601 units. */
export const isTimeDimension = (dimension: OfferingDimension): boolean =>
    /^(?:dim_)?time$/i.test(dimension.name) || dimension.units === 'ISO8601';

/** The time a request URL asks for, whatever case its parameter was written in; undefined when it asks the server default. */
export const getTimeParameter = (url: URL): string | undefined =>
    [...url.searchParams.entries()].find(([name]) => isTimeParameter(name))?.[1];

/**
 * Replace the time parameter of a request however it was written; an empty value hands it back to the
 * server default. A written TIME is replaced in the position it already has, because a time which moves
 * through the query is another url for the very same image — the buffering of the neighbouring frames
 * only answers the overlay when both sides ask under one identical key. Only a foreign spelling (a
 * lowercase time or a DIM_TIME) becomes the canonical TIME, which moves it once before the identity of
 * the request settles (#823).
 */
export const setTimeParameter = (params: URLSearchParams, value: string): void => {
    const [first, ...duplicates] = [...params.keys()].filter(isTimeParameter);
    duplicates.forEach(name => params.delete(name));
    if (first !== undefined && first !== 'TIME') params.delete(first);
    if (value === '') {
        params.delete('TIME');
        return;
    }
    if (first === 'TIME') params.set(first, value);
    else params.append('TIME', value);
};

/** The name one dimension's request parameter carries in this URL, whatever case it was written in. */
const findDimensionParameter = (params: URLSearchParams, name: string): string | undefined => {
    const parameter = getDimensionParameter(name).toUpperCase();
    return [...params.keys()].find(key => key.toUpperCase() === parameter);
};

/** The value a request carries for one dimension; undefined when it asks the server default. */
export const readDimensionValue = (params: URLSearchParams, name: string): string | undefined => {
    const key = findDimensionParameter(params, name);
    return key === undefined ? undefined : params.get(key) ?? undefined;
};

/**
 * Replace one dimension's value in the position its parameter already has, so the request keeps its
 * identity for the buffering; an empty value removes the parameter and hands the dimension back to the
 * server default. A spelling which differs from the canonical parameter is renamed in that very
 * position — URLSearchParams could only rename by moving to the end, which is another identity —
 * and further spellings the service left behind are dropped.
 */
export const writeDimensionValue = (params: URLSearchParams, name: string, value: string): void => {
    const parameter = getDimensionParameter(name);
    const entries = [...params.entries()];
    let replaced = false;
    [...params.keys()].forEach(key => params.delete(key));
    for (const [key, entry] of entries) {
        if (key.toUpperCase() !== parameter.toUpperCase()) {
            params.append(key, entry);
            continue;
        }
        if (!replaced && value !== '') params.append(parameter, value);
        replaced = true;
    }
    if (!replaced && value !== '') params.append(parameter, value);
};

/** The time a request asks for under one dimension — the well known TIME also answers its legacy spellings. */
export const getTimeValueOfDimension = (params: URLSearchParams, name: string): string | undefined =>
    /^(?:dim_)?time$/i.test(name)
        ? [...params.entries()].find(([key]) => isTimeParameter(key))?.[1]
        : readDimensionValue(params, name);

/**
 * Replace the time a request carries for one dimension. The well known TIME goes through
 * setTimeParameter, which also unifies the legacy spellings; a DIM_<name> dimension is written in
 * place under its own parameter.
 */
export const writeTimeForDimension = (params: URLSearchParams, name: string, value: string): void => {
    if (/^(?:dim_)?time$/i.test(name)) setTimeParameter(params, value);
    else writeDimensionValue(params, name, value);
};

/** The time the URL asks for under the offering's time dimension: the well known TIME or a DIM_<name>. */
export const getOfferingTimeValue = (url: URL, offering?: Offering): string | undefined =>
    getTimeValueOfDimension(url.searchParams,
        (offering?.dimensions ?? []).find(isTimeDimension)?.name ?? 'time');

/** The value the requests of this offering currently carry: the last selection or the advertised default. */
export const getWmsDimensionSelection = (offering: Offering, dimension: OfferingDimension): string => {
    const parameter = getDimensionParameter(dimension.name);
    const operation = offering.operations?.find(item => item.code === 'GetMap')
        ?? offering.operations?.find(item => item.code === 'GetFeatureInfo');
    if (operation === undefined) return '';
    const url = new URL(operation.href);
    const current = parameter === 'TIME'
        ? getTimeParameter(url)
        : [...url.searchParams.entries()].find(([key]) => key.toUpperCase() === parameter)?.[1];
    return current ?? dimension.default ?? '';
};

/**
 * Write one advertised dimension's value into both WMS operations of the offering, or remove the
 * parameter when the map user chooses the server default again. Values the service does not offer
 * are refused, and independent GetMap/GetFeatureInfo activation survives the change.
 */
export const setWmsDimension = (offering: Offering, name: string, value: string): void => {
    const dimension = offering.dimensions?.find(item => item.name === name);
    if (dimension === undefined || !isAllowedDimensionValue(dimension, value)) return;
    const parameter = getDimensionParameter(name);
    offering.operations
        ?.filter(operation => ['GetMap', 'GetFeatureInfo'].includes(operation.code))
        .forEach(operation => {
            const url = new URL(operation.href);
            if (parameter === 'TIME') setTimeParameter(url.searchParams, value);
            else writeDimensionValue(url.searchParams, name, value);
            operation.href = url.href;
        });
};

/** Non-default selections shown beside the layer, using the same values as its requests. */
export const getWmsDimensionOverrides = (offering?: Offering) =>
    (offering?.dimensions ?? []).flatMap(dimension => {
        const value = getWmsDimensionSelection(offering!, dimension);
        if (value === '' || value === dimension.default) return [];
        const selection = parseInstant(value);
        const advertisedDefault = parseInstant(dimension.default ?? '');
        if (selection !== undefined && advertisedDefault !== undefined && selection === advertisedDefault) return [];
        return [{ name: dimension.name, value }];
    });

/**
 * Anchor calendar steps at the advertised start, without enumerating large time ranges. The start and
 * the step are parsed once: a range of a million observations is walked by its positions, so reading
 * its text again for every position is the cost that must not be paid.
 */
const timeRangeInstantAt = (range: Extract<AdvertisedValues, { kind: 'time-range' }>): ((index: number) => number) | undefined => {
    const start = parseInstant(range.start);
    const step = range.step === undefined ? undefined : parseDuration(range.step);
    if (start === undefined || step === undefined) return undefined;
    return (index: number) => stepInstant(start, step, index);
};

/** The discrete observations a time dimension advertises, as positions a viewer can step through. */
export type TimeDimensionAxis = {
    count: number
    valueAt: (index: number) => string
    indexOf: (value: string) => number
}

/**
 * The positions approached next from `index`, nearest first: up to `ahead` onwards — back to the first
 * observation at the end of the range when `loop` returns there — and up to `behind` backwards, which
 * scrubbing reaches for while an animation only ever walks onwards. A position outside a range which
 * does not loop is left out, so nothing is named that the service does not advertise (#705).
 */
export const getUpcomingTimeAxisPositions = (axis: TimeDimensionAxis, index: number, upcoming: {
    ahead: number
    behind?: number
    loop?: boolean
}): number[] => {
    const { ahead, behind = 0, loop = false } = upcoming;
    if (index < 0 || index >= axis.count) return [];
    const positions: number[] = [];
    for (let distance = 1; distance <= Math.max(ahead, behind); distance++) {
        const onwards = index + distance;
        if (distance <= ahead && (onwards < axis.count || loop))
            positions.push(onwards < axis.count ? onwards : onwards % axis.count);
        if (distance <= behind && index - distance >= 0) positions.push(index - distance);
    }
    return [...new Set(positions)].filter(position => position !== index && position < axis.count);
};

/** the axis of a stepped temporal interval: its observations up to the advertised end */
const steppedTimeRangeAxis = (advertised: Extract<AdvertisedValues, { kind: 'time-range' }>) => {
    const instantAt = timeRangeInstantAt(advertised);
    if (instantAt === undefined) return undefined;
    const increasing = instantAt(1) > instantAt(0);
    if (!increasing) return undefined;
    const stop = parseInstant(advertised.stop);
    if (stop === undefined) return undefined;
    let low = 0, high = 1;
    while (instantAt(high) <= stop && high < Number.MAX_SAFE_INTEGER / 2) high *= 2;
    while (low + 1 < high) {
        const middle = Math.floor((low + high) / 2);
        if (instantAt(middle) <= stop) low = middle;
        else high = middle;
    }
    return {
        count: low + 1,
        instantAt,
        valueAt: (index: number) => formatInstant(instantAt(index)),
    };
};

/** the axis of a listed series of instants: the distinct values in temporal order */
const listedTimeAxis = (advertised: Extract<AdvertisedValues, { kind: 'list' }>) => {
    const observations = [...new Set(advertised.values)].flatMap(value => {
        const instant = parseInstant(value);
        return instant === undefined ? [] : [{ instant, value }];
    }).sort((a, b) => a.instant - b.instant);
    return {
        count: observations.length,
        instantAt: (index: number) => observations[index].instant,
        valueAt: (index: number) => observations[index].value,
    };
};

/** A slider position names an available timestamp, even for calendar or irregular steps. */
export const getTimeDimensionAxis = (dimension: OfferingDimension) => {
    if (!isTimeDimension(dimension)) return undefined;
    const advertised = parseAdvertisedValues(dimension.values);
    let axis: ReturnType<typeof steppedTimeRangeAxis>;
    if (advertised.kind === 'time-range' && advertised.step) {
        axis = steppedTimeRangeAxis(advertised);
    } else if (advertised.kind === 'list' && advertised.values.length > 0 && advertised.values.every(isInstant)) {
        axis = listedTimeAxis(advertised);
    } else return undefined; // Continuous ranges retain their exact date input.
    if (axis === undefined) return undefined;
    const { count, instantAt, valueAt } = axis;
    const indexOf = (value: string) => {
        const target = parseInstant(value);
        if (target === undefined) return -1;
        let low = 0, high = count - 1;
        while (low <= high) {
            const middle = Math.floor((low + high) / 2), instant = instantAt(middle);
            if (instant === target) return middle;
            if (instant < target) low = middle + 1;
            else high = middle - 1;
        }
        return -1;
    };
    return { count, valueAt, indexOf };
};

/**
 * The offering's dimension whose advertised values form the axis a viewer steps through, with that
 * axis — the buffering needs both: the axis to name the upcoming observations and the dimension to
 * write them into the request under the very parameter the timeline selected them with.
 */
export const getSteppedTimeDimension = (offering?: Offering) =>
    (offering?.dimensions ?? []).flatMap(dimension => {
        const axis = getTimeDimensionAxis(dimension);
        return axis === undefined ? [] : [{ dimension, axis }];
    })[0];
