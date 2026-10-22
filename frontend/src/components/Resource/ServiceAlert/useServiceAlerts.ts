import { useEffect } from "react";
import { useDataProvider, useGetList } from "react-admin";

export const ALERT_REFETCH_INTERVAL = 20000;

const useServiceAlerts = () => {
  const provider = useDataProvider();
  const result = useGetList(
    "ServiceAlert",
    {
      pagination: { page: 1, perPage: 5 },
      sort: { field: "severity,-occurredAt", order: "ASC" },
      filter: {},
    },
    { refetchInterval: ALERT_REFETCH_INTERVAL, retry: false },
  );
  const { refetch } = result;
  useEffect(() => {
    const refresh = () => {
      void refetch();
    };
    provider.subscribe("resource/ServiceAlert", refresh);
    return () => {
      provider.unsubscribe("resource/ServiceAlert", refresh);
    };
  }, [provider, refetch]);
  return result;
};

export default useServiceAlerts;
