import { type ReactElement } from 'react';

import MrMapFrontend from './components/MrMapFrontend';
import { HttpClientBase } from './context/HttpClientContext';
import { OwsContextBase } from './react-ows-lib/ContextProvider/OwsContextBase';


export const App = (): ReactElement => {



  return (
    <HttpClientBase>
      <OwsContextBase>
        <MrMapFrontend />
      </OwsContextBase>
    </HttpClientBase>
  )
}
