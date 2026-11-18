import { describe, expect, test } from 'vitest';

import {
    formatInstant,
    isInstant,
    isPositiveDuration,
    parseDuration,
    parseInstant,
    stepInstant,
} from './iso8601';

describe('the instants of the WMS time grammar', () => {
    test('reads a date alone as the midnight of its UTC day', () => {
        expect(parseInstant('2024-01-01')).toBe(Date.UTC(2024, 0, 1));
        // a year below 100 is the case `Date.UTC` maps into the twentieth century
        expect(formatInstant(parseInstant('0001-01-01')!)).toBe('0001-01-01T00:00:00.000Z');
    });

    test('reads the time of day down to the millisecond, with either separator', () => {
        expect(parseInstant('2024-01-01T06:30')).toBe(Date.UTC(2024, 0, 1, 6, 30));
        expect(parseInstant('2024-01-01t06:30:15')).toBe(Date.UTC(2024, 0, 1, 6, 30, 15));
        expect(parseInstant('2024-01-01 06:30:15.250Z')).toBe(Date.UTC(2024, 0, 1, 6, 30, 15, 250));
        expect(parseInstant('2024-01-01T06:30:15,25Z')).toBe(Date.UTC(2024, 0, 1, 6, 30, 15, 250));
    });

    test('keeps an instant without an offset in UTC, which is the zone the service advertises in', () => {
        // Date.parse would read these as the wall clock of the viewer and move the observation
        expect(parseInstant('2024-01-01T06:30')).toBe(parseInstant('2024-01-01T06:30Z'));
        expect(parseInstant('2024-01-01T06:30')).toBe(parseInstant('2024-01-01T06:30:00.000z'));
    });

    test('moves an advertised offset onto UTC, with or without its colon', () => {
        expect(parseInstant('2024-01-01T06:30:00+02:00')).toBe(Date.UTC(2024, 0, 1, 4, 30));
        expect(parseInstant('2024-01-01T06:30:00+0200')).toBe(Date.UTC(2024, 0, 1, 4, 30));
        expect(parseInstant('2024-01-01T06:30:00-05:30')).toBe(Date.UTC(2024, 0, 1, 12));
        expect(parseInstant('2024-01-01T06:30+02')).toBe(Date.UTC(2024, 0, 1, 4, 30));
    });

    test('reads the fraction down to the millisecond, which is all a Date holds', () => {
        expect(parseInstant('2024-01-01T00:00:00.5Z')).toBe(Date.UTC(2024, 0, 1, 0, 0, 0, 500));
        expect(parseInstant('2024-01-01T00:00:00.0009Z')).toBe(Date.UTC(2024, 0, 1));
        expect(parseInstant('2024-01-01T00:00:00.123456Z')).toBe(Date.UTC(2024, 0, 1, 0, 0, 0, 123));
    });

    test('reads a leap second as the moment its minute ends', () => {
        // no Date holds a second of 60; the leap second of the 30th of June ends the June day
        expect(parseInstant('2025-06-30T23:59:60Z')).toBe(Date.UTC(2025, 6, 1));
        expect(parseInstant('2025-06-30T23:59:60Z')).toBe(parseInstant('2025-07-01T00:00:00Z'));
    });

    test('refuses what the grammar does not read, instead of guessing a moment', () => {
        expect(parseInstant('')).toBeUndefined();
        expect(parseInstant('current')).toBeUndefined();
        expect(parseInstant('2024-13-01')).toBeUndefined();
        expect(parseInstant('2024-02-30')).toBeUndefined();
        expect(parseInstant('2024-01-00')).toBeUndefined();
        expect(parseInstant('24-01-01')).toBeUndefined();
        expect(parseInstant('20240101')).toBeUndefined();
        expect(parseInstant('2024-01-01T24:00')).toBeUndefined();
        expect(parseInstant('2024-01-01T24:00:00Z')).toBeUndefined();
        expect(parseInstant('2024-01-01T23:60')).toBeUndefined();
        expect(parseInstant('2024-01-01T23:59:61Z')).toBeUndefined();
        expect(parseInstant('2024-01-01T06:30+99:00')).toBeUndefined();
        expect(parseInstant('2024-01-01T06:30Z extra')).toBeUndefined();
        expect(isInstant('2024-01-01T06:30Z')).toBe(true);
        expect(isInstant('2024-02-30')).toBe(false);
    });

    test('answers the canonical UTC text a request carries its TIME in', () => {
        expect(formatInstant(parseInstant('2024-05-21T21:00Z')!)).toBe('2024-05-21T21:00:00.000Z');
        expect(formatInstant(parseInstant('2024-01-01')!)).toBe('2024-01-01T00:00:00.000Z');
        expect(formatInstant(parseInstant('2024-01-01T00:00:00+02:00')!)).toBe('2023-12-31T22:00:00.000Z');
    });
});

describe('the duration a time dimension steps by', () => {
    test('binds every amount to the unit it names', () => {
        expect(parseDuration('P1D')).toEqual({ months: 0, ms: 86400000 });
        expect(parseDuration('P2W')).toEqual({ months: 0, ms: 14 * 86400000 });
        expect(parseDuration('PT5M')).toEqual({ months: 0, ms: 300000 });
        expect(parseDuration('PT0.25S')).toEqual({ months: 0, ms: 250 });
        expect(parseDuration('P0.5D')).toEqual({ months: 0, ms: 43200000 });
        expect(parseDuration('P1Y2M3DT4H5M6S')).toEqual({ months: 14, ms: 3 * 86400000 + 14706000 });
    });

    test('counts the calendar units as months, the finest unit an observation steps by', () => {
        expect(parseDuration('P1M')).toEqual({ months: 1, ms: 0 });
        expect(parseDuration('P1Y')).toEqual({ months: 12, ms: 0 });
        expect(parseDuration('P1.5Y')).toEqual({ months: 18, ms: 0 });
        // a fractional month names no amount of months to step by, so it names no step
        expect(parseDuration('P1.5M')).toBeUndefined();
        expect(parseDuration('P0.5M')).toBeUndefined();
    });

    test('refuses what is not a duration of the grammar', () => {
        expect(parseDuration('')).toBeUndefined();
        expect(parseDuration('P')).toBeUndefined();
        expect(parseDuration('PT')).toBeUndefined();
        expect(parseDuration('1D')).toBeUndefined();
        expect(parseDuration('p1d')).toBeUndefined();
        expect(parseDuration('P1S')).toBeUndefined();
        expect(parseDuration('PT1D')).toBeUndefined();
        expect(parseDuration('P2M1Y')).toBeUndefined();
        expect(parseDuration('P-1D')).toBeUndefined();
        expect(parseDuration('PT.5S')).toBeUndefined();
        expect(parseDuration('P1DT')).toBeUndefined();
    });

    test('says whether the duration moves an observation on at all', () => {
        expect(isPositiveDuration(parseDuration('P1D')!)).toBe(true);
        expect(isPositiveDuration(parseDuration('P1M')!)).toBe(true);
        expect(isPositiveDuration(parseDuration('P0D')!)).toBe(false);
        expect(isPositiveDuration(parseDuration('P0M')!)).toBe(false);
        expect(isPositiveDuration(parseDuration('PT0.0S')!)).toBe(false);
    });
});

describe('the observation a step names', () => {
    const start = parseInstant('2024-01-31')!;

    test('stays at the observation it starts from', () => {
        expect(stepInstant(start, parseDuration('P1M')!, 0)).toBe(start);
        expect(stepInstant(start, parseDuration('PT15M')!, 0)).toBe(start);
    });

    test('keeps the day of the month a monthly step advertises and falls back where it is not', () => {
        const month = parseDuration('P1M')!;
        // the same day of every month, and the last day it has where the 31st does not exist
        expect(formatInstant(stepInstant(start, month, 1))).toBe('2024-02-29T00:00:00.000Z');
        expect(formatInstant(stepInstant(start, month, 2))).toBe('2024-03-31T00:00:00.000Z');
        expect(formatInstant(stepInstant(start, month, 3))).toBe('2024-04-30T00:00:00.000Z');
        expect(formatInstant(stepInstant(start, month, 4))).toBe('2024-05-31T00:00:00.000Z');
        // a century which is not a leap year has 28 days in February
        expect(formatInstant(stepInstant(parseInstant('2100-01-31')!, month, 1)))
            .toBe('2100-02-28T00:00:00.000Z');
        // and a year step from a leap day falls to the last day of February as well
        expect(formatInstant(stepInstant(parseInstant('2024-02-29')!, parseDuration('P1Y')!, 1)))
            .toBe('2025-02-28T00:00:00.000Z');
    });

    test('adds the length of a step which names none of the calendar units', () => {
        const minutes = parseInstant('2011-02-16T00:00:00Z')!;
        expect(stepInstant(minutes, parseDuration('PT5M')!, 3)).toBe(minutes + 900000);
        expect(formatInstant(stepInstant(start, parseDuration('P0.5D')!, 1)))
            .toBe('2024-01-31T12:00:00.000Z');
    });

    test('applies the calendar months before the length of a mixed step', () => {
        // the length is the same for every observation and must not be moved by the clamp
        expect(formatInstant(stepInstant(start, parseDuration('P1MT12H')!, 1)))
            .toBe('2024-02-29T12:00:00.000Z');
    });

    test('counts a step over the turn of a year', () => {
        const december = parseInstant('2024-12-31T23:59:59Z')!;
        expect(formatInstant(stepInstant(december, parseDuration('P1Y')!, 1)))
            .toBe('2025-12-31T23:59:59.000Z');
        expect(formatInstant(stepInstant(december, parseDuration('P1M')!, 13)))
            .toBe('2026-01-31T23:59:59.000Z');
    });
});
