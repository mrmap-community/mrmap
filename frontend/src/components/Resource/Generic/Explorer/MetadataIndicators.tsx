import { useMemo } from "react";
import {
  useListContext,
  useTranslate,
  type RaRecord,
} from "react-admin";

import { Chip, Stack } from "@mui/material";

import { Count } from "../../../../jsonapi/components/Count";

/**
 * The quality, licence and coverage indicators of metadata results.
 *
 * The states are read from the attributes of the record itself, exactly as the
 * api names them in a response, and an absent attribute stays unknown: a missing
 * field is never rendered as a passed check. The chips and the facet strip link
 * to the filtered list, so an indicator and the facet which counts it are one
 * and the same state.
 *
 * The metadata date (`dateStamp`) is deliberately not an indicator here - it is
 * the date of the document and says nothing about a harvest, which the states
 * below do.
 */
export const INDICATOR_FILTER_KEYS: string[] = [
  "is_broken",
  "has_insufficient_quality",
  "has_coverage",
  "has_licence",
];

/** The filters of a query without the indicators, so a facet counts its own state only. */
export const withoutIndicatorKeys = (filter?: Record<string, unknown>): Record<string, unknown> =>
  Object.fromEntries(
    Object.entries(filter ?? {}).filter(([key]) => !INDICATOR_FILTER_KEYS.includes(key)),
  );

/** The query a list answers, so a facet counts the same records as the rows below it. */
export const queryOfList = (
  filter?: Record<string, unknown>,
  filterValues?: Record<string, unknown>,
): Record<string, unknown> => ({ ...filterValues, ...filter });

export type IndicatorState = "ok" | "warning" | "error" | "unknown";

export const indicatorStates = (record: RaRecord): { key: string; state: IndicatorState }[] => {
  const indicators: { key: string; state: IndicatorState }[] = [];
  // an absent attribute is unknown and never a passed check
  indicators.push({
    key: "broken",
    state: record.isBroken === true ? "error" : record.isBroken === false ? "ok" : "unknown",
  });
  const quality = record.insufficientQuality;
  indicators.push({
    key: "quality",
    state:
      typeof quality === "string"
        ? quality.trim() === ""
          ? "ok"
          : "warning"
        : "unknown",
  });
  // the licence arrives as a json:api relationship, which the data provider may
  // answer unwrapped; a null in any shape is the explicit statement that the
  // record names no licence and an absent value stays unknown. Coverage has its
  // own chip in the result row already and is only counted as a facet here.
  const licence = record.licence as { data?: unknown } | null | undefined;
  const licenceData = licence !== null && typeof licence === "object" && "data" in licence ? licence.data : licence;
  indicators.push({
    key: "licence",
    state:
      licence === undefined || licenceData === undefined
        ? "unknown"
        : licenceData === null
          ? "warning"
          : "ok",
  });
  return indicators;
};

const CHIP_COLOR: Record<IndicatorState, "default" | "success" | "warning" | "error"> = {
  ok: "success",
  warning: "warning",
  error: "error",
  unknown: "default",
};

/** The filter a state is chosen with; a passed check asks the opposite of its warning. */
const FILTER_OF_STATE: Record<string, Partial<Record<IndicatorState, Record<string, unknown>>>> = {
  broken: { error: { is_broken: true }, ok: { is_broken: false } },
  quality: { warning: { has_insufficient_quality: true }, ok: { has_insufficient_quality: false } },
  coverage: { warning: { has_coverage: false }, ok: { has_coverage: true } },
  licence: { warning: { has_licence: false }, ok: { has_licence: true } },
};

export const indicatorFilter = (key: string, state: IndicatorState): Record<string, unknown> | undefined =>
  FILTER_OF_STATE[key]?.[state];

/**
 * The compact chips of one result row. Every chip carries the state word, a
 * passed check reads as success and an unknown one stays neutral; clicking a
 * chip of a warning or an error narrows the list to its state, which is the
 * detail the user can act on.
 */
export const MetadataIndicators = ({ record }: { record: RaRecord }) => {
  const translate = useTranslate();
  const { filter, filterValues, setFilters, resource } = useListContext();
  const scope = useMemo(
    () => withoutIndicatorKeys(queryOfList(filter, filterValues)),
    [filter, filterValues],
  );
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
      {indicatorStates(record).map(({ key, state }) => {
        const filterOfState = indicatorFilter(key, state);
        const label = translate(`metadataIndicators.${key}.${state}`);
        const choosable = state !== "ok" && state !== "unknown" && filterOfState !== undefined && resource !== undefined;
        return (
          <Chip
            key={key}
            size="small"
            variant="outlined"
            color={CHIP_COLOR[state]}
            label={label}
            onClick={choosable ? () => setFilters({ ...scope, ...filterOfState }, {}) : undefined}
          />
        );
      })}
    </Stack>
  );
};

/** The facets the strip counts, each one a filter of the api and nothing else. */
export const metadataFacets: { key: string; filter: Record<string, unknown> }[] = [
  { key: "broken", filter: { is_broken: true } },
  { key: "quality", filter: { has_insufficient_quality: true } },
  { key: "coverage", filter: { has_coverage: false } },
  { key: "licence", filter: { has_licence: false } },
];

/**
 * The facet strip above a metadata result list: one count per state, asked of the
 * api over the complete authorized query and never over the current page. The
 * scope is the query of the list without the indicator filters, so a facet counts
 * its own state and the strip and a chosen chip never answer two contradictory
 * filters at once.
 */
export const MetadataFacets = () => {
  const { filter, filterValues, resource } = useListContext();
  const translate = useTranslate();
  const scope = useMemo(
    () => withoutIndicatorKeys(queryOfList(filter, filterValues)),
    [filter, filterValues],
  );
  if (resource === undefined) return null;
  return (
    <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1, px: 2, pt: 1 }}>
      {metadataFacets.map((facet) => (
        <Chip
          key={facet.key}
          size="small"
          variant="outlined"
          label={
            <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
              <span>{translate(`metadataIndicators.facets.${facet.key}`)}</span>
              <Count resource={resource} filter={{ ...scope, ...facet.filter }} link />
            </Stack>
          }
        />
      ))}
    </Stack>
  );
};
