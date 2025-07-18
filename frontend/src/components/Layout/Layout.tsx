import { useRef, useState, type ReactNode } from 'react';
import { Layout, type Identifier, type LayoutProps } from 'react-admin';
import { ReadyState } from 'react-use-websocket';

import CircleIcon from '@mui/icons-material/Circle';
import GitHubIcon from '@mui/icons-material/GitHub';
import { Box, Grid, IconButton, Tooltip, Typography } from '@mui/material';
import Card from '@mui/material/Card';
import useResizeObserver from '@react-hook/resize-observer';
import { SnackbarProvider } from 'notistack';

import { useHttpClientContext } from '../../context/HttpClientContext';
import I18Observer from '../../jsonapi/components/I18Observer';
import RealtimeBus from '../../jsonapi/components/Realtime/RealtimeBus';
import SnackbarObserver from '../../jsonapi/components/Realtime/SnackbarObserver';
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
  const { api } = useHttpClientContext();
  const readyState = '1'
  const footerRef = useRef(null);
  const [footerHeight, setFooterHeight] = useState<number>();
  
  useResizeObserver(footerRef ?? null, (entry) => setFooterHeight(entry.contentRect.height))

  return (
    <SnackbarProvider
      maxSnack={10}
      // action={SnackbarCloseButton}
      Components={
        {
          taskProgress: SnackbarContentBackgroundProcess
        }
      }
    >
      <RealtimeBus/> 
      <I18Observer/>
      <Layout
        appBar={MrMapAppBar}
        menu={Menu}
        sx={{
           marginTop: '0', 
           '& .RaLayout-appFrame': { marginTop: '0 !important' },
           '& .RaLayout-content': { width: '200px'}, // this width is needed, otherwise the container will not resize dynimcly
        }}
        {...rest}
      >
        <Box 
          style={{ 
            margin: "10px", 
            marginBottom: footerHeight,
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
          textAlign: 'center',
        }}>
          <Grid container spacing={2} sx={{ justifyContent: 'space-between' }} ref={footerRef}>
          
            <Grid >
              <Typography padding={1}> v.{api?.document.info.version}</Typography>
            </Grid>

            <Grid  >
              <IconButton href="https://github.com/mrmap-community" target="_blank">
                <GitHubIcon />
              </IconButton>
            </Grid>

            <Grid  alignItems="center" >
              <Tooltip title={readyState === ReadyState.OPEN ? 'Backend is connected': 'Connection to backend lost'}>
                <IconButton padding={1} >
                  <CircleIcon
                    color={readyState === ReadyState.OPEN ? 'success': 'error'}
                  />
                </IconButton>
              </Tooltip>
            </Grid>
          
          </Grid>
        </Card>
       
      </Layout>
    </SnackbarProvider>

  )
}

export default MyLayout
