import { store } from '@/services/ReduxStore/Store';
import type { ReactElement } from 'react';
import { useEffect } from 'react';
import useWebSocket from 'react-use-websocket';

export default function WebSockets (props: any): ReactElement {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const hostname = window.location.hostname;
  const port = window.location.port;
  const defaultWsUrl = scheme + '://' + hostname + ':' + port + '/ws/default/';

  const lastMessage = useWebSocket(defaultWsUrl, {
    shouldReconnect: () => { return true; },
    reconnectInterval: 3000
  });

  const handleMessage = (lastJsonMessage: any) => {
    // TODO: check if the schema matches
    store.dispatch(lastJsonMessage);
  };

  useEffect(() => {
    if (lastMessage !== null && lastMessage.lastJsonMessage) {
        handleMessage(lastMessage.lastJsonMessage);
    }
  }, [lastMessage]);

  return props.children;
}