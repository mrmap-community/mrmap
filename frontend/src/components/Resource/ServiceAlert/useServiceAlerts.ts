import { useEffect } from "react";
import { useDataProvider, useGetList } from "react-admin";
import { ReadyState } from "react-use-websocket";

import { useHttpClientContext } from "../../../context/HttpClientContext";

export const ALERT_REFETCH_INTERVAL = 20000;

/**
 * The alerts which need the attention of an administrator.
 *
 * @param filter the alerts to ask for, as the api of the alerts answers them -
 *  every alert of the deployment by default
 */
const useServiceAlerts = (
  filter: Record<string, string | number | undefined> = {},
) => {
  const provider = useDataProvider();
  const { realtimeIsReady } = useHttpClientContext();
  const result = useGetList(
    "ServiceAlert",
    {
      pagination: { page: 1, perPage: 5 },
      sort: { field: "severity,-occurredAt", order: "ASC" },
      filter,
    },
    {
      // the bus carries the alert topic - it only polls while that is down
      refetchInterval: realtimeIsReady === ReadyState.OPEN ? false : ALERT_REFETCH_INTERVAL,
      retry: false,
    },
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
