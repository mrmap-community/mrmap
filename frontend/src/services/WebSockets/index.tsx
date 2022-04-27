import { store } from '@/services/ReduxStore/Store';
import type { ReactElement } from 'react';
import { useEffect } from 'react';
import useWebSocket from 'react-use-websocket';

export default function WebSockets(props: any): ReactElement {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const hostname = window.location.hostname;
  const port = window.location.port;
  const defaultWsUrl = scheme + '://' + hostname + ':' + port + '/ws/default/';

  const { lastJsonMessage } = useWebSocket(defaultWsUrl, {
    shouldReconnect: () => {
      return true;
    },
    reconnectInterval: 3000,
  });

  useEffect(() => {
    if (lastJsonMessage !== null) {
      store.dispatch(lastJsonMessage);
    }
  }, [lastJsonMessage]);

  return props.children;
}
