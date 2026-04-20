import { useMemo, type ReactNode } from 'react';
import { Layout, useTheme, type Identifier, type LayoutProps } from 'react-admin';
import { ReadyState } from 'react-use-websocket';

import { Box } from '@mui/material';
import { SnackbarProvider } from 'notistack';

import { useHttpClientContext } from '../../context/HttpClientContext';
import I18Observer from '../../jsonapi/components/I18Observer';
import RealtimeBus from '../../jsonapi/components/Realtime/RealtimeBus';
import SnackbarObserver from '../../jsonapi/components/Realtime/SnackbarObserver';
import { useSystemTime } from '../../jsonapi/hooks/useSystemTime';
import SnackbarContentBackgroundProcess from '../Resource/BackgroundProcess/ShowShortInfoBackgroundProcess';
import MrMapAppBar from './AppBar';
import Menu from './Menu';


declare module 'notistack' {
  interface VariantOverrides {
    // adds `taskProgress` variant and specifies the
    // "extra" props it takes in options of `enqueueSnackbar`
    taskProgress: {
      taskId: Identifier
    }
  }
}

// Dirty hack to append SnackbarObserver
const MyLayout = (
  {
    children,
    ...rest
  }: LayoutProps
): ReactNode => {
  const { api, realtimeIsReady } = useHttpClientContext();
  const systemTime = useSystemTime();
  const theme = useTheme();

  const readyStateColor = useMemo(()=>{
    switch(realtimeIsReady){
      case ReadyState.CONNECTING:
        return 'warning'
      case ReadyState.OPEN:
        return 'success'
      case ReadyState.CLOSING:
      case ReadyState.CLOSED:
        return 'error'
      case ReadyState.UNINSTANTIATED:
      default:
        return 'info'

    }
  },[realtimeIsReady])

  return (
    <SnackbarProvider
      maxSnack={10}
      // action={SnackbarCloseButton}
      Components={{
          taskProgress: SnackbarContentBackgroundProcess
      }}
    >
      <RealtimeBus/> 
      <I18Observer/>
      <Layout
        appBar={MrMapAppBar}
        menu={Menu}
        sx={{
          height: '100vh',
          maxHeight: '100vh',
          
          display: 'flex',
          flexDirection: 'column',
          '& .RaLayout-appFrame': {
            marginTop: '0 !important',
            marginBottom: '50px',
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: 0
          },

          '& .RaLayout-content': {
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden', // prevent double scrollbars
            minHeight: 0,
            marginBottom: '50px',
          },
        }}
        {...rest}
      >
        {/* MAIN SCROLLABLE CONTENT */}
        <Box sx={{ 
            flex: 1, 
            minHeight: 0, // allow shrinking to fit the viewport
            overflow: 'auto',
            m: 1
          }}
        >
          {children}
          {<SnackbarObserver />}
        </Box>       
      </Layout>
    </SnackbarProvider>

  )
}

export default MyLayout
