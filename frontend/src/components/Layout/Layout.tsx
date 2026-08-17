import { type ReactNode } from 'react';
import { Layout, type Identifier, type LayoutProps } from 'react-admin';

import { Box, Card } from '@mui/material';
import { SnackbarProvider } from 'notistack';

import I18Observer from '../../jsonapi/components/I18Observer';
import RealtimeBus from '../../jsonapi/components/Realtime/RealtimeBus';
import SnackbarObserver from '../../jsonapi/components/Realtime/SnackbarObserver';
import SnackbarContentBackgroundProcess from '../Resource/BackgroundProcess/ShowShortInfoBackgroundProcess';
import MrMapAppBar from './AppBar';
import Footer from './Footer';
import CustomMenu from './Menu';


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
        menu={CustomMenu}
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
        <Card style={{
              position: 'fixed',
              right: 0, 
              bottom: 0, 
              left: 0, 
              zIndex: 100,
        }}>
          <Footer/>
        </Card>   
      </Layout>
    </SnackbarProvider>

  )
}

export default MyLayout
