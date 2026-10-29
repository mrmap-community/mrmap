import type { Offering, OfferingDimension } from './types';

import moment from 'moment';

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

/**
 * Read advertised numeric and ISO 8601 temporal intervals without expanding large ranges.
 */
export const parseAdvertisedValues = (values: string): AdvertisedValues => {
    const parts = values.split('/');
    if (parts.length >= 2 && parts.length <= 3
        && parts.every(part => part.trim() !== '' && Number.isFinite(Number(part)))) {
        const start = Number(parts[0]);
        const stop = Number(parts[1]);
        const step = parts.length === 3 ? Number(parts[2]) : undefined;
        return { kind: 'range', start, stop, ...(step !== undefined && step > 0 ? { step } : {}) };
    }
    if ((parts.length === 2 || parts.length === 3) &&
        moment.utc(parts[0], moment.ISO_8601, true).isValid() &&
        moment.utc(parts[1], moment.ISO_8601, true).isValid() &&
        moment.utc(parts[0]).valueOf() <= moment.utc(parts[1]).valueOf() &&
        (parts[2] === undefined || (/^P(?=.+)(?:\d+(?:\.\d+)?Y)?(?:\d+(?:\.\d+)?M)?(?:\d+(?:\.\d+)?W)?(?:\d+(?:\.\d+)?D)?(?:T(?=.+)(?:\d+(?:\.\d+)?H)?(?:\d+(?:\.\d+)?M)?(?:\d+(?:\.\d+)?S)?)?$/.test(parts[2]) && moment.duration(parts[2]).asMilliseconds() > 0))) {
        return { kind: 'time-range', start: parts[0], stop: parts[1], ...(parts[2] && { step: parts[2] }) };
    }
    return { kind: 'list', values: values.split(',').map(value => value.trim()).filter(Boolean) };
};

/** The empty value stands for the server default and is always allowed. */
export const isAllowedDimensionValue = (dimension: OfferingDimension, value: string): boolean => {
    if (value === '') return true;
    const advertised = parseAdvertisedValues(dimension.values);
    if (advertised.kind === 'list')
        return advertised.values.includes(value) || value === dimension.default;
    if (advertised.kind === 'time-range') {
        if (value === dimension.default || value === dimension.values) return true;
        const instant = moment.utc(value, moment.ISO_8601, true);
        const start = moment.utc(advertised.start);
        const stop = moment.utc(advertised.stop);
        if (!instant.isValid() || instant.isBefore(start) || instant.isAfter(stop)) return false;
        if (!advertised.step) return true;
        const at = (index: number) => timeRangeInstant(advertised, index);
        let low = 0, high = 1;
        while (at(high) < instant.valueOf() && high < Number.MAX_SAFE_INTEGER / 2) high *= 2;
        while (low <= high) {
            const middle = Math.floor((low + high) / 2);
            const candidate = at(middle);
            if (candidate === instant.valueOf()) return true;
            if (candidate < instant.valueOf()) low = middle + 1;
            else high = middle - 1;
        }
        return false;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return false;
    if (numeric < Math.min(advertised.start, advertised.stop)
        || numeric > Math.max(advertised.start, advertised.stop)) return false;
    if (advertised.step === undefined) return true;
    const position = (numeric - advertised.start) / advertised.step;
    return Math.abs(position - Math.round(position)) < 1e-9;
};

/** Whether a request parameter name carries the WMS time dimension, in any written case and with or without the DIM_ prefix. */
export const isTimeParameter = (name: string): boolean =>
    /^(?:dim_)?time$/i.test(name);

/** The time a request URL asks for, whatever case its parameter was written in; undefined when it asks the server default. */
export const getTimeParameter = (url: URL): string | undefined =>
    [...url.searchParams.entries()].find(([name]) => isTimeParameter(name))?.[1];

/** Replace the time parameter of a request however it was written; an empty value hands it back to the server default. */
export const setTimeParameter = (params: URLSearchParams, value: string): void => {
    [...params.keys()].filter(isTimeParameter).forEach(name => params.delete(name));
    if (value !== '') params.set('TIME', value);
};

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
            else {
                [...url.searchParams.keys()]
                    .filter(key => key.toUpperCase() === parameter)
                    .forEach(key => url.searchParams.delete(key));
                if (value !== '') url.searchParams.set(parameter, value);
            }
            operation.href = url.href;
        });
};

/** Non-default selections shown beside the layer, using the same values as its requests. */
export const getWmsDimensionOverrides = (offering?: Offering) =>
    (offering?.dimensions ?? []).flatMap(dimension => {
        const value = getWmsDimensionSelection(offering!, dimension);
        if (value === '' || value === dimension.default) return [];
        const a = moment.utc(value, moment.ISO_8601, true);
        const b = moment.utc(dimension.default ?? '', moment.ISO_8601, true);
        if (a.isValid() && b.isValid() && a.isSame(b)) return [];
        return [{ name: dimension.name, value }];
    });

// Anchor calendar steps at the advertised start, without enumerating large time ranges.
const timeRangeInstant = (range: Extract<AdvertisedValues, { kind: 'time-range' }>, index: number) => {
    const duration = moment.duration(range.step);
    const milliseconds = duration.days() * 86400000 + duration.hours() * 3600000 +
        duration.minutes() * 60000 + duration.seconds() * 1000 + duration.milliseconds();
    return moment.utc(range.start)
        .add((duration.years() * 12 + duration.months()) * index, 'months')
        .add(milliseconds * index, 'milliseconds').valueOf();
};

/** A slider position names an available timestamp, even for calendar or irregular steps. */
export const getTimeDimensionAxis = (dimension: OfferingDimension) => {
    if (!/^(?:dim_)?time$/i.test(dimension.name) && dimension.units !== 'ISO8601') return undefined;
    const advertised = parseAdvertisedValues(dimension.values);
    let count: number;
    let instantAt: (index: number) => number;
    let valueAt: (index: number) => string;
    if (advertised.kind === 'time-range' && advertised.step) {
        instantAt = index => timeRangeInstant(advertised, index);
        if (!(instantAt(1) > instantAt(0))) return undefined;
        const stop = moment.utc(advertised.stop).valueOf();
        let low = 0, high = 1;
        while (instantAt(high) <= stop && high < Number.MAX_SAFE_INTEGER / 2) high *= 2;
        while (low + 1 < high) {
            const middle = Math.floor((low + high) / 2);
            if (instantAt(middle) <= stop) low = middle;
            else high = middle;
        }
        count = low + 1;
        valueAt = index => moment.utc(instantAt(index)).toISOString();
    } else if (advertised.kind === 'list' && advertised.values.length > 0 && advertised.values.every(value => moment.utc(value, moment.ISO_8601, true).isValid())) {
        const values = [...new Set(advertised.values)].sort((a, b) => moment.utc(a).valueOf() - moment.utc(b).valueOf());
        count = values.length;
        instantAt = index => moment.utc(values[index]).valueOf();
        valueAt = index => values[index];
    } else return undefined; // Continuous ranges retain their exact date input.
    const indexOf = (value: string) => {
        const target = moment.utc(value, moment.ISO_8601, true).valueOf();
        if (!Number.isFinite(target)) return -1;
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
