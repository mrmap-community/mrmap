import { type Identifier, type RaRecord, useGetList, useTranslate } from "react-admin";

import { Stack, Typography } from "@mui/material";

/**
 * The runs a throughput of a catalogue is measured by.
 *
 * The window is asked wider than the recommendation needs: a run which never
 * finished answers no throughput and is not part of the measurement, so the runs
 * which do answer one are fewer than the ones which were asked.
 */
const RUNS_TO_ASK = 10;

/** the attribute which names the page size a harvesting run asked with */
const SIZE = "maxStepSize";

/** the attribute which names the records per minute a harvesting run measured */
const THROUGHPUT = "recordsPerMinute";

interface SizeMeasurement {
  /** the page size the runs of this group asked the catalogue with */
  size: number;
  /** the records per minute those runs measured between them */
  throughput: number;
  /** how many runs measured this size */
  runs: number;
}

interface HarvestThroughputHintProps {
  /** the catalogue whose harvesting runs measured the throughput */
  serviceId: Identifier;
  /** the size the catalogue is harvested with today */
  currentSize?: number;
}

const numberOf = (run: RaRecord, attribute: string) => {
  const value = run[attribute];
  return typeof value === "number" ? value : undefined;
};

/** the page size and the throughput of the runs which measured a throughput of their own */
const sizesMeasured = (runs: RaRecord[]): SizeMeasurement[] => {
  const groups = new Map<number, SizeMeasurement>();
  runs.forEach((run) => {
    const size = numberOf(run, SIZE);
    const throughput = numberOf(run, THROUGHPUT);
    if (size === undefined || throughput === undefined || throughput <= 0) {
      return;
    }
    const known = groups.get(size);
    groups.set(
      size,
      known
        ? {
            size,
            throughput: known.throughput + throughput,
            runs: known.runs + 1,
          }
        : { size, throughput, runs: 1 },
    );
  });
  return Array.from(groups.values())
    .map((group) => ({ ...group, throughput: group.throughput / group.runs }))
    .sort((first, second) => second.throughput - first.throughput);
};

/**
 * What the harvests of a catalogue measured per page size, and the fastest one.
 *
 * The size a harvest starts with is a decision about a remote service, which
 * nobody can make from the couch: the runs a catalogue already has behind it
 * measured it. They are asked from the endpoint of the harvesting runs itself,
 * which answers the throughput of a completed run next to the size it asked
 * with, so this is the measurement of the catalogue and not a comparison with a
 * default (#692).
 *
 * A catalogue whose runs never finished, or whose runs carry no durations,
 * answers no throughput - and this answers nothing instead of a recommendation
 * which was never measured.
 */
const HarvestThroughputHint = ({
  serviceId,
  currentSize,
}: HarvestThroughputHintProps) => {
  const translate = useTranslate();
  const { data = [] } = useGetList("HarvestingJob", {
    filter: { service__id: serviceId },
    // the runs which ended last: the harvesting never set the creation of a run
    sort: { field: "doneAt", order: "DESC" },
    pagination: { page: 1, perPage: RUNS_TO_ASK },
    meta: {
      jsonApiParams: {
        "fields[HarvestingJob]": "id,done_at,max_step_size,records_per_minute",
      },
    },
  });
  const sizes = sizesMeasured(data);
  if (sizes.length === 0) return null;
  const fastest = sizes[0];
  const measured = sizes.reduce((count, size) => count + size.runs, 0);
  return (
    <Stack spacing={0.25}>
      <Typography variant="caption" color="text.secondary">
        {translate("harvestThroughput.basis", { count: measured })}
      </Typography>
      {sizes.map((size) => (
        <Typography
          key={size.size}
          variant="caption"
          sx={{ fontWeight: size.size === fastest.size ? 600 : 400 }}
        >
          {translate("harvestThroughput.perPage", {
            size: size.size,
            throughput: Math.round(size.throughput),
          })}
        </Typography>
      ))}
      <Typography variant="caption">
        {translate(
          currentSize === fastest.size
            ? "harvestThroughput.isFastest"
            : "harvestThroughput.recommendation",
          { size: fastest.size },
        )}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {translate("harvestThroughput.measuredBy")}
      </Typography>
    </Stack>
  );
};

export default HarvestThroughputHint;
