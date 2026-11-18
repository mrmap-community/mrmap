import { useEffect, useMemo } from "react";
import { useAuthState, useDataProvider } from "react-admin";
import useWebSocket, { ReadyState } from "react-use-websocket";

import { useHttpClientContext } from "../../../context/HttpClientContext";


const { VITE_API_SCHEMA, VITE_API_BASE_URL, VITE_API_PORT } = import.meta.env;


const RealtimeBus = () => {
  const { authenticated } = useAuthState();
  const dataProvider = useDataProvider();
  const  {setRealtimeIsReady} = useHttpClientContext();

  // No credential in this URL (#835): the WebSocket handshake is same-origin,
  // so the browser attaches the session cookie and
  // `channels.auth.AuthMiddlewareStack` resolves the user from it. A token in
  // the query string would have put the live credential into access logs, the
  // browser history and every referer the page hands on - the path the backend
  // still accepts for old clients only, and deprecates in `notify/auth.py`.
  const websocketUrl = useMemo(()=>{
      return `${VITE_API_SCHEMA === "https" ? "wss": "ws"}://${VITE_API_BASE_URL}:${VITE_API_PORT}/ws/default/`
    },[])

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
  },[readyState, dataProvider, getWebSocket, setRealtimeIsReady])

  return null
};

export default RealtimeBus;