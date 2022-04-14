import type { ReactElement } from 'react';
import { useEffect } from 'react';
import { useDispatch } from 'react-redux';
import useWebSocket from 'react-use-websocket';

export default function WebSockets(props: any): ReactElement {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const hostname = window.location.hostname;
  const port = window.location.port;
  const defaultWsUrl = scheme + '://' + hostname + ':' + port + '/ws/default/';
  const dispatch = useDispatch();

  const lastMessage = useWebSocket(defaultWsUrl, {
    shouldReconnect: () => {
      return true;
    },
    reconnectInterval: 3000,
  });

  useEffect(() => {
    if (lastMessage !== null && lastMessage.lastJsonMessage) {
      // TODO: check if the schema matches
      dispatch(lastMessage.lastJsonMessage);
    }
  }, [dispatch, lastMessage]);

  return props.children;
}
