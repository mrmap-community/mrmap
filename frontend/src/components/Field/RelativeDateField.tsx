import { type ReactNode } from "react";
import { type RaRecord, useFieldValue } from "react-admin";

import { Typography, type SxProps, type Theme } from "@mui/material";

export interface RelativeDateFieldProps {
  /** the attribute of the record which answers the moment */
  source: string;
  /** the record to read the moment at, which is the record of the screen if unset */
  record?: RaRecord;
  /** the locale the distance and the absolute moment are formatted with */
  locales?: string;
  /** what to answer for a record which names no moment, which is nothing by default */
  emptyText?: ReactNode;
  /** the style of the text */
  sx?: SxProps<Theme>;
}

/**
 * The units a distance in time is answered with, from the coarsest to the
 * finest, and how many milliseconds one of them holds.
 *
 * `Intl.RelativeTimeFormat` answers a distance by a single unit, so the coarsest
 * unit which still holds the whole distance is the one which is asked - the
 * distance to a moment a night ago is "14 hours ago" and never "5040 minutes".
 */
const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 1000 * 60 * 60 * 24 * 365],
  ["month", 1000 * 60 * 60 * 24 * 30],
  ["week", 1000 * 60 * 60 * 24 * 7],
  ["day", 1000 * 60 * 60 * 24],
  ["hour", 1000 * 60 * 60],
  ["minute", 1000 * 60],
  ["second", 1000],
];

/** the moment a record answers, or nothing when it answers none */
const asDate = (value: unknown): Date | undefined => {
  const date = value instanceof Date ? value : new Date(String(value ?? ""));
  return Number.isNaN(date.getTime()) ? undefined : date;
};

/** the distance from now to the given moment, by the coarsest unit which holds it */
const distanceToNow = (date: Date, locales?: string): string => {
  const milliseconds = date.getTime() - Date.now();
  const [unit, held] =
    UNITS.find(([, millisecondsOfUnit]) =>
      Math.abs(milliseconds) >= millisecondsOfUnit,
    ) ?? UNITS[UNITS.length - 1];
  return new Intl.RelativeTimeFormat(locales, { numeric: "auto" }).format(
    Math.round(milliseconds / held),
    unit,
  );
};

/**
 * The moment a record names, as the distance to now ("3 hours ago") with the
 * absolute moment in its title.
 *
 * A row of a list is read for its distance to now: whether the run which decided
 * a service ended before the night or after it is the question a screen of
 * services is asked, and the exact moment is only wanted once that distance is
 * known. `DateField` of react-admin answers the absolute moment and nothing
 * else, which is why the distance is formatted here with the browser's own
 * `Intl.RelativeTimeFormat` and no further dependency; the absolute moment stays
 * readable in the title of the text, formatted by the same locale.
 *
 * Nothing is shown for a record which answers no moment: whether that is an
 * absence is a question of the screen around the field, which says it in its own
 * words - and names them in `emptyText` when the row should say so.
 */
const RelativeDateField = ({
  source,
  record,
  locales,
  emptyText,
  sx,
}: RelativeDateFieldProps): ReactNode => {
  const date = asDate(useFieldValue({ source, record }));
  if (date === undefined) {
    return emptyText === undefined ? null : (
      <Typography variant="body2" color="text.secondary" sx={sx}>
        {emptyText}
      </Typography>
    );
  }

  return (
    <Typography
      component="span"
      variant="body2"
      color="text.secondary"
      title={new Intl.DateTimeFormat(locales, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date)}
      sx={{ whiteSpace: "nowrap", ...sx }}
    >
      {distanceToNow(date, locales)}
    </Typography>
  );
};

export default RelativeDateField;
