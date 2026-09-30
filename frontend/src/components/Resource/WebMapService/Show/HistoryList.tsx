import UpdateIcon from "@mui/icons-material/Update";
import {
  Alert,
  alpha,
  Card,
  CardHeader,
  FormControl,
  MenuItem,
  Select,
} from "@mui/material";
import { useMemo, useState } from "react";
import {
  Loading,
  type RaRecord,
  type SimpleListProps,
  useGetList,
  useRecordContext,
  useTranslate,
} from "react-admin";
import HistoryTimeline, { type HistoryRecord } from "./HistoryTimeline";

export interface HistoryListProps extends SimpleListProps {
  related: string;
  record: RaRecord | undefined;
}

type ChangeType = "all" | "WebMapService" | "Layer";

const HistoryList = ({ record }: HistoryListProps) => {
  const [changeType, setChangeType] = useState<ChangeType>("all");
  const translate = useTranslate();
  const recordContext = useRecordContext(record);
  
  const wmsJsonApiParams = useMemo(() => {
    const params: Record<string, string | number> = { include: "historyUser" };
    params["fields[User]"] = "username,string_representation";
    if (recordContext !== undefined && recordContext.id !== undefined) {
      params["filter[historyRelation]"] = recordContext.id;
    }
    return params;
  }, [recordContext]);

  const layerJsonApiParams = useMemo(() => {
    const params: Record<string, string | number> = {
      include: "historyUser",
    };
    params["fields[HistoricalLayer]"] =
      "history_type,delta,history_date,history_relation,title";
    params["fields[User]"] = "username,string_representation";
    if (recordContext !== undefined && recordContext.id !== undefined) {
      params["filter[service]"] = recordContext.id;
    }
    return params;
  }, [recordContext]);

  const {
    data: wmsChanges,
    isLoading: wmsIsLoading,
    error: wmsError,
  } = useGetList<HistoryRecord>(
    "HistoricalWebMapService",
    {
      filter: {
        changed_or_created: true,
      },
      sort: {
        field: "historyDate",
        order: "DESC",
      },
      pagination: {
        page: 1,
        perPage: 100,
      },
      meta: {
        jsonApiParams: wmsJsonApiParams,
      },
    },
    {
      enabled:
        recordContext?.id != null &&
        (changeType === "all" || changeType === "WebMapService"),
    },
  );
  const {
    data: layerChanges,
    isLoading: layerIsLoading,
    error: layerError,
  } = useGetList<HistoryRecord>(
    "HistoricalLayer",
    {
      filter: {
        changed_or_deleted: true,
      },
      sort: {
        field: "historyDate",
        order: "DESC",
      },
      pagination: {
        page: 1,
        perPage: 100,
      },
      meta: {
        jsonApiParams: layerJsonApiParams,
      },
    },
    {
      enabled:
        recordContext?.id != null &&
        (changeType === "all" || changeType === "Layer"),
    },
  );

  const mixedChanges = useMemo(() => {
    return [
      ...(wmsChanges?.map((record) => ({
        ...record,
        _type: "WebMapService" as const,
      })) ?? []),

      ...(layerChanges?.map((record) => ({
        ...record,
        _type: "Layer" as const,
      })) ?? []),
    ].sort(
      (a, b) =>
        new Date(b.historyDate).getTime() - new Date(a.historyDate).getTime(),
    );
  }, [wmsChanges, layerChanges]);

  const filteredChanges = useMemo(
    () =>
      mixedChanges.filter(
        (change) => changeType === "all" || change._type === changeType,
      ),
    [mixedChanges, changeType],
  );

  const loading =
    (changeType !== "Layer" && wmsIsLoading) ||
    (changeType !== "WebMapService" && layerIsLoading);
  const error =
    (changeType !== "Layer" && wmsError) ||
    (changeType !== "WebMapService" && layerError);

  return (
    <Card
      variant="outlined"
      sx={{
        borderColor: "secondary.main",
        minWidth: 0,
        maxWidth: "100%",
        height: "100%"
      }}
    >
      <CardHeader
        title={translate("resources.ChangeLog.lastChanges")}
        subheader="Select an event to inspect its details."
        avatar={<UpdateIcon />}
        action={
          <FormControl size="small">
            <Select
              value={changeType}
              onChange={(event) =>
                setChangeType(event.target.value as ChangeType)
              }
              inputProps={{ "aria-label": "Filter history by resource" }}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="all">
                All changes ({mixedChanges.length})
              </MenuItem>
              <MenuItem value="WebMapService">
                Service changes ({wmsChanges?.length ?? 0})
              </MenuItem>
              <MenuItem value="Layer">
                Layer changes ({layerChanges?.length ?? 0})
              </MenuItem>
            </Select>
          </FormControl>
        }
        sx={(theme) => ({
          bgcolor: alpha(theme.palette.secondary.main, 0.08),
          flexWrap: "wrap",
          gap: 1,
          "& .MuiCardHeader-action": { m: 0 },
          "& .MuiCardHeader-content": { minWidth: 150 },
        })}
      />
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
    </Card>
  );
};

export default HistoryList;
