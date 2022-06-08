import type { JsonApiPrimaryData } from '@/utils/jsonapi';
import { useEffect, useState } from 'react';
import useWebSocket from 'react-use-websocket';
import type { WebSocketHook } from 'react-use-websocket/dist/lib/types';

export interface DefaultWebSocket extends WebSocketHook {
  lastResourceMessage: any;
}

export interface WebSocketMessage {
  type: string;
  payload: JsonApiPrimaryData;
}

export const useDefaultWebSocket = (resourceTypes: string[] = []): DefaultWebSocket => {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const hostname = window.location.hostname;
  const port = window.location.port;
  const defaultWsUrl = scheme + '://' + hostname + ':' + port + '/ws/default/';

  const [lastResourceMessage, setLastResourceMessage] = useState<WebSocketMessage>();

  const { lastJsonMessage, lastMessage, sendMessage, sendJsonMessage, readyState, getWebSocket } =
    useWebSocket(defaultWsUrl, {
      shouldReconnect: () => {
        return true;
      },
      reconnectInterval: 3000,
      share: true,
    });

  useEffect(() => {
    if (lastJsonMessage?.payload?.type) {
      const inform =
        resourceTypes.length > 0
          ? resourceTypes.find((resourceType) =>
              lastJsonMessage.payload.type.includes(resourceType),
            )
          : true;
      if (inform) {
        setLastResourceMessage(lastJsonMessage);
      }
    }
  }, [lastJsonMessage, resourceTypes]);

  return {
    lastResourceMessage,
    lastJsonMessage,
    lastMessage,
    sendMessage,
    sendJsonMessage,
    readyState,
    getWebSocket,
  };
};
