import { type ReactElement } from 'react';

import MrMapFrontend from './components/MrMapFrontend';
import { HttpClientBase } from './context/HttpClientContext';


export const App = (): ReactElement => {



  return (
    <HttpClientBase>
      <MrMapFrontend />
    </HttpClientBase>
  )
}
