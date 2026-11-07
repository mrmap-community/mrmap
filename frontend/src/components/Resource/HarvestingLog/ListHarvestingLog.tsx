import { type ReactElement } from "react";
import {
  BooleanField,
  DateField,
  FunctionField,
  ShowButton,
  useListContext,
  useRecordContext,
  useTranslate,
  WrapperField,
} from "react-admin";

import {
  Chip,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import { type RelatedResource } from "../../../providers/dataProvider";
import TruncatedTextField from "../../Field/TruncatedTextField";
import ListActions from "../../Lists/CustomListActions";

export interface ListHarvestingLogProps {
  /** the run whose log lines are listed, which is the parent of the nested route */
  relatedResource?: Partial<RelatedResource>;
  /** passed to the list: a running run keeps its page fresh, a closed one does not */
  refetchInterval?: number | false;
  /** passed to the list: a tab of a run does not persist its list parameters */
  storeKey?: string | false;
}

/**
 * The words of the log scale, at the number the api answers each at
 * (`registry/enums/harvesting.py:LogLevelEnum`, 0 the loudest).
 */
const LEVEL_WORDS = ["fatal", "error", "warning", "info", "debug"];

/**
 * The narrowings the header offers, each one the filter it sets: the scale
 * counts down to the loudest, so "and above" is a `level__lte` (#1080).
 */
const FACETS: Array<{ key: string; filter?: Record<string, number> }> = [
  { key: "all" },
  { key: "infoAndAbove", filter: { level__lte: 3 } },
  { key: "warningsAndAbove", filter: { level__lte: 2 } },
];

const levelWord = (level: unknown): string | undefined =>
  LEVEL_WORDS[Number(level)];

/**
 * The level facet of the log and the log level the run was told to write at,
 * beside the rows they narrow - a run logging at INFO answered nothing about
 * a page which came back short, so its level belongs next to the lines (#1083).
 */
const LogLevelHeader = (): ReactElement => {
  const translate = useTranslate();
  const { filterValues, displayedFilters, setFilters } = useListContext();
  const run = useRecordContext();
  const chosen =
    FACETS.find(
      (facet) =>
        facet.filter !== undefined &&
        Number(filterValues?.level__lte) === facet.filter.level__lte,
    )?.key ?? "all";
  const choose = (key: string) => {
    const rest = { ...filterValues };
    delete rest.level__lte;
    const facet = FACETS.find((candidate) => candidate.key === key);
    setFilters({ ...rest, ...(facet?.filter ?? {}) }, displayedFilters);
  };
  const runLevel = levelWord(run?.logLevel);
  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ p: 2, alignItems: "center", flexWrap: "wrap", gap: 1 }}
    >
      <ToggleButtonGroup
        exclusive
        size="small"
        value={chosen}
        onChange={(_, key: string | null) => choose(key ?? "all")}
        aria-label={translate("harvestRun.logLevelFacets")}
      >
        {FACETS.map((facet) => (
          <ToggleButton key={facet.key} value={facet.key}>
            {translate(`harvestRun.logFacets.${facet.key}`)}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      {runLevel !== undefined && (
        <Typography variant="body2" color="text.secondary">
          {translate("harvestRun.runLogLevel", {
            level: translate(`harvestRun.logLevels.${runLevel}`),
          })}
        </Typography>
      )}
    </Stack>
  );
};

/**
 * The log lines of one run, in the order of their own timestamps.
 *
 * The list answers whether a stored response hangs behind a line
 * (`hasExtendedDescription`) and never its content: the file is read per
 * line, by the detail route, which the show button opens and which is gated
 * by the read access of the run (#1083, #888).
 */
const ListHarvestingLog = ({
  relatedResource,
  refetchInterval = false,
  storeKey,
}: ListHarvestingLogProps): ReactElement => {
  const translate = useTranslate();
  return (
    <ListGuesser
      resource="HarvestingLog"
      relatedResource={relatedResource}
      sort={{ field: "timestamp", order: "DESC" }}
      storeKey={storeKey}
      refetchInterval={refetchInterval}
      header={<LogLevelHeader />}
      rowActions={
        <WrapperField label="harvestRun.logLine">
          <ShowButton />
        </WrapperField>
      }
      ActionsComponent={(props) => (
        <ListActions {...props} isConfigureable={false} isExportable={false} />
      )}
      columns={[
        <DateField
          key="timestamp"
          source="timestamp"
          showTime
          label="harvestRun.logTimestamp"
        />,
        <FunctionField
          key="level"
          source="level"
          label="harvestRun.logLevelLabel"
          render={(record) => {
            const word = levelWord(record?.level);
            if (word === undefined) return null;
            return (
              <Chip
                size="small"
                color={
                  word === "fatal" || word === "error"
                    ? "error"
                    : word === "warning"
                      ? "warning"
                      : "default"
                }
                label={translate(`harvestRun.logLevels.${word}`)}
              />
            );
          }}
        />,
        <FunctionField
          key="kind"
          source="kind"
          sortable={false}
          label="harvestRun.logKind"
          render={(record) =>
            record?.kind == null
              ? null
              : translate(
                  `harvestRun.logKinds.${record.kind === 1 ? "countMismatch" : "remoteError"}`,
                )
          }
        />,
        <TruncatedTextField
          key="description"
          source="description"
          label="harvestRun.logDescription"
        />,
        <BooleanField
          key="hasExtendedDescription"
          source="hasExtendedDescription"
          label="harvestRun.storedResponse"
        />,
      ]}
    />
  );
};

export default ListHarvestingLog;
