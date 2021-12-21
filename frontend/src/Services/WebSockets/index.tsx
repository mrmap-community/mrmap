import React, { useEffect } from 'react';
import useWebSocket from 'react-use-websocket';

import { store } from '../ReduxStore/Store';

export default function WebSockets (): JSX.Element {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const hostname = window.location.hostname;
  const port = window.location.port;
  const defaultWsUrl = scheme + '://' + hostname + ':' + port + '/ws/default/';

  const lastMessage = useWebSocket(defaultWsUrl, {
    shouldReconnect: () => { return true; },
    reconnectInterval: 3000
  });

  const handleMessage = (lastJsonMessage:any) => {
    // TODO: check if the schema matches
    store.dispatch(lastJsonMessage);
  };

  useEffect(() => {
    if (lastMessage !== null && lastMessage.lastJsonMessage) {
      // eslint-disable-next-line
        handleMessage(lastMessage.lastJsonMessage);
    }
    // eslint-disable-next-lint
  }, [lastMessage]);

  // TODO: clairify if this is a common way to outsource global code
  return (
      <div></div>
  );
}
