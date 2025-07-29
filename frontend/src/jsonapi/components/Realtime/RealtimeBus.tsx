import { useEffect, useMemo } from "react";
import { useAuthState, useDataProvider } from "react-admin";
import useWebSocket, { ReadyState } from "react-use-websocket";
import { useHttpClientContext } from "../../../context/HttpClientContext";
import { getAuthToken } from "../../../providers/authProvider";


const { VITE_API_SCHEMA, VITE_API_BASE_URL } = import.meta.env;


const RealtimeBus = () => {
  const { authenticated } = useAuthState();
  const dataProvider = useDataProvider();
  const  {setRealtimeIsReady} = useHttpClientContext();

  const websocketUrl = useMemo(()=>{
      if (authenticated){
        const storedAuthToken = getAuthToken();
        return `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}/ws/default/?token=${storedAuthToken?.token}`
      } else {
        return `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}/ws/default/`
      }
    },[authenticated])

  const { readyState, getWebSocket } = useWebSocket(
      websocketUrl,
      {
        shouldReconnect: () => true,
        reconnectAttempts: 10,
        //attemptNumber will be 0 the first time it attempts to reconnect, so this equation results in a reconnect pattern of 1 second, 2 seconds, 4 seconds, 8 seconds, and then caps at 10 seconds until the maximum number of attempts is reached
        reconnectInterval: (attemptNumber) => Math.min(Math.pow(2, attemptNumber) * 1000, 10000)
      },
      !!authenticated
    );

  useEffect(()=>{
    if (readyState === ReadyState.OPEN){
      const websocket = getWebSocket()
      dataProvider.attachRealtimeOnMessage(websocket)
    }
    setRealtimeIsReady(readyState)
  },[readyState])

  return (
    <></>
  )
};

export default RealtimeBus;