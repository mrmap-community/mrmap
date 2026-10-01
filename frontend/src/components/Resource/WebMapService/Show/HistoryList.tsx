import { useMemo } from "react";
import { historicalSource } from "../../Generic/History/historySources";
import type { RaRecord, SimpleListProps } from "react-admin";
import ServiceHistoryList from "../../Generic/History/ServiceHistoryList";

export interface HistoryListProps extends SimpleListProps {
  related: string;
  record: RaRecord | undefined;
}

export default function HistoryList({ record }: HistoryListProps) {
  const sources = useMemo(() => record ? [
    historicalSource("HistoricalWebMapService", "WebMapService", "Service changes", record.id, "historyRelation"),
    historicalSource("HistoricalLayer", "Layer", "Layer changes", record.id, "service"),
  ] : [], [record?.id]);
  return <ServiceHistoryList key={record?.id} sources={sources} record={record} />;
}
