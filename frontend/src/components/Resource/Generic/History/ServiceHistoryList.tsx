import UpdateIcon from "@mui/icons-material/Update";
import { Alert, alpha, FormControl, MenuItem, Select } from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import {
  Loading,
  type RaRecord,
  useGetList,
  useRecordContext,
  useTranslate,
} from "react-admin";
import SimpleCard from "../../../MUI/SimpleCard";
import type { HistorySource } from "./historySources";
import HistoryTimeline, { type TimelineRecord } from "./HistoryTimeline";

export interface ServiceHistoryListProps {
  sources: HistorySource[];
  record?: RaRecord;
}

// Each source owns its query hook, so adding a feed never changes hook order.
function HistorySourceQuery({ source, onChange }: { source: HistorySource; onChange: (resource: string, result: FeedResult) => void }) {
  const { data, isPending, error } = useGetList(source.resource, {
    filter: source.filter,
    sort: { field: "historyDate", order: "DESC" },
    pagination: { page: 1, perPage: 100 },
    meta: { jsonApiParams: source.jsonApiParams ?? {} },
  });
  useEffect(() => {
    onChange(source.resource, { events: (data ?? []).map(source.toEvent), loading: isPending, error });
  }, [data, isPending, error, source, onChange]);
  return null;
}

interface FeedResult {
  events: TimelineRecord[];
  loading: boolean;
  error?: unknown;
}

const ServiceHistoryList = ({ record, sources }: ServiceHistoryListProps) => {
  const [changeType, setChangeType] = useState("all");
  const [feeds, setFeeds] = useState<Record<string, FeedResult>>({});
  const translate = useTranslate();
  const recordContext = useRecordContext(record);
  const onChange = useCallback((resource: string, result: FeedResult) => {
    setFeeds(previous => ({ ...previous, [resource]: result }));
  }, []);
  const selectedSources = sources.filter(source => changeType === "all" || source.type === changeType);
  const mixedChanges = sources.flatMap(source => feeds[source.resource]?.events ?? []);
  const filteredChanges = selectedSources.flatMap(source => feeds[source.resource]?.events ?? []).sort((a, b) => new Date(b.historyDate).getTime() - new Date(a.historyDate).getTime());
  const loading = selectedSources.some(source => !feeds[source.resource] || feeds[source.resource].loading);
  const error = selectedSources.some(source => feeds[source.resource]?.error);

  return (
    <SimpleCard
      divider={false}
      contentProps={false}
      cardProps={{
        variant: "outlined",
        sx: {
          borderColor: "secondary.main",
          minWidth: 0,
          width: "100%",
          height: "100%",
        },
      }}

      title={translate("resources.ChangeLog.lastChanges")}
      subheader="Select an event to inspect its details."
      headerProps={{
        avatar: <UpdateIcon />,
        action: sources.length > 1 ? (
          <FormControl size="small">
            <Select
              value={changeType}
              onChange={(event) =>
                setChangeType(event.target.value)
              }
              inputProps={{ "aria-label": "Filter history by resource" }}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="all">
                All changes ({mixedChanges.length})
              </MenuItem>
              {sources.map(source => <MenuItem key={source.resource} value={source.type}>
                {translate(source.label, { _: source.label })} ({feeds[source.resource]?.events.length ?? 0})
              </MenuItem>)}
            </Select>
          </FormControl>
        ) : undefined,
        sx: (theme) => ({
          bgcolor: alpha(theme.palette.secondary.main, 0.08),
          flexWrap: "wrap",
          gap: 1,
          "& .MuiCardHeader-action": { m: 0 },
          "& .MuiCardHeader-content": { minWidth: 150 },
        }),
      }}
    >
      {recordContext?.id != null && sources.map(source => <HistorySourceQuery key={source.resource} source={source} onChange={onChange} />)}
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert severity="error">Unable to load history.</Alert>
      ) : (
        <HistoryTimeline
          key={`${recordContext?.id}:${changeType}`}
          events={filteredChanges}
        />
      )}
    </SimpleCard>
  );
};

export default ServiceHistoryList;
