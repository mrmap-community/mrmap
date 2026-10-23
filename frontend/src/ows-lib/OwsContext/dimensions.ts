import type { Offering, OfferingDimension } from './types';

/**
 * WMS asks the request for an advertised dimension through a well known parameter:
 * "elevation" answers as ELEVATION and every other advertised name as DIM_<name>.
 */
export const getDimensionParameter = (name: string): string => {
    const trimmed = name.trim();
    if (trimmed.toLowerCase() === 'elevation') return 'ELEVATION';
    return `DIM_${trimmed.replace(/^dim_/i, '').toUpperCase()}`;
};

export type AdvertisedValues =
    | { kind: 'list'; values: string[] }
    | { kind: 'range'; start: number; stop: number; step?: number };

/**
 * The stated value text of a dimension. Only a slash separated numeric pair or triple counts as a
 * range; everything else - including ISO 8601 time spans - stays a list of selectable values.
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
    return { kind: 'list', values: values.split(',').map(value => value.trim()).filter(Boolean) };
};

/** The empty value stands for the server default and is always allowed. */
export const isAllowedDimensionValue = (dimension: OfferingDimension, value: string): boolean => {
    if (value === '') return true;
    const advertised = parseAdvertisedValues(dimension.values);
    if (advertised.kind === 'list')
        return advertised.values.includes(value) || value === dimension.default;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return false;
    if (numeric < Math.min(advertised.start, advertised.stop)
        || numeric > Math.max(advertised.start, advertised.stop)) return false;
    if (advertised.step === undefined) return true;
    const position = (numeric - advertised.start) / advertised.step;
    return Math.abs(position - Math.round(position)) < 1e-9;
};

/** The value the requests of this offering currently carry: the last selection or the advertised default. */
export const getWmsDimensionSelection = (offering: Offering, dimension: OfferingDimension): string => {
    const parameter = getDimensionParameter(dimension.name);
    const operation = offering.operations?.find(item => item.code === 'GetMap')
        ?? offering.operations?.find(item => item.code === 'GetFeatureInfo');
    if (operation === undefined) return '';
    const current = [...new URL(operation.href).searchParams.entries()]
        .find(([key]) => key.toUpperCase() === parameter)?.[1];
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
            [...url.searchParams.keys()]
                .filter(key => key.toUpperCase() === parameter)
                .forEach(key => url.searchParams.delete(key));
            if (value !== '') url.searchParams.set(parameter, value);
            operation.href = url.href;
        });
};
