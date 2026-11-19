import { type ReactNode } from 'react';
import { Layout, useSidebarState, type LayoutProps } from 'react-admin';

import { Box, Card } from '@mui/material';

import { SystemStatusProvider } from '../../context/SystemStatusContext';
import I18Observer from '../../jsonapi/components/I18Observer';
import RealtimeBus from '../../jsonapi/components/Realtime/RealtimeBus';
import BackgroundJobBridge from '../Resource/BackgroundProcess/BackgroundJobBridge';
import BackgroundJobCenterProvider from '../Resource/BackgroundProcess/JobCenter/BackgroundJobCenterContext';
import IncidentCenterProvider from '../Resource/OperationalIncident/IncidentCenter/IncidentCenterContext';
import MrMapAppBar from './AppBar';
import BreadCrump from './BreadCrump';
import Footer from './Footer';
import CustomMenu from './Menu';
import PermissionLostBridge from './PermissionLostBridge';


// wraps the Admin layout and mounts the renderless observers: the realtime bus,
// the locale observer and the notification bridge of the background jobs (#1205)
// which turns the failures the Background Job Center reports into aggregated
// notifications. The Background Job Center (#1203) is mounted here as well and
// owns the job state, the hydration and every realtime subscription (#1461);
// the feedback of ordinary user actions runs on react-admin's own notifications
// (`useNotify`). There is deliberately no custom snackbar stack: a persisting
// snackbar per background process is exactly the flooding the Job Center
// replaced.
const MyLayout = (
  {
    children,
    ...rest
  }: LayoutProps
): ReactNode => {
  const [open] = useSidebarState()


  return (
    <SystemStatusProvider>
      {/* the center owns the store and the subscriptions; the thin bridge
          below subscribes its failure seam and is the mounted notification
          path (#1205, converged into one store in #1461) — the center's own
          announcement is silent here so one failure never becomes two
          toasts */}
      <BackgroundJobCenterProvider notifications={false}>
      {/* the incident center (#1321): its provider owns the two bounded
          windows, the app bar indicator reads them through the context and
          the drawer mounts with the provider - no incident ever announces
          as a snackbar, the center is the announcement */}
      <IncidentCenterProvider>
        <RealtimeBus/> 
        <I18Observer/>
        <BackgroundJobBridge />
        <PermissionLostBridge />
      <Layout
        appBar={MrMapAppBar}
        menu={CustomMenu}
        sx={{
          height: '100vh',
          maxHeight: '100vh',
          minWidth: 0,
          
          display: 'flex',
          flexDirection: 'column',
          '& .RaLayout-contentWithSidebar': {
            flex: 1,
            minHeight: 0,
          },
          '& .RaSidebar-docked': {
            height: 'auto',
            minHeight: 0,
            marginBottom: '40px',
            '& .MuiPaper-root': {
              height: '100%',
            },
            '& .RaSidebar-fixed': {
              position: 'absolute',
              height: '100%',
            },
          },
          '& .RaLayout-appFrame': {
            marginTop: '0 !important',
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
            marginBottom: '40px',
          },
          '& .RaList-main': {
            width: `calc(${open ? '60vw' : '80vw'} - ${open ? '240px' : '50px'} - 3em)`,
            //maxHeight: 'calc(50vh - 174px )', // 174px ==> 50 appbar, 52 pagination, 64 table actions, 8 top padding
            overflowX: 'hidden',
            marginLeft: "1em",
            marginRight: "1em",
            marginBottom: "1em",
          },
          '& .RaShow-main': {
            width: `calc(100vw - ${open ? '240px' : '50px'}  - 3em)`,
            //maxHeight: 'calc(50vh - 174px )', // 174px ==> 50 appbar, 52 pagination, 64 table actions, 8 top padding
            overflowX: 'hidden',
            marginLeft: "1em",
            marginRight: "1em",
            marginBottom: "1em",
          },
          '& .RaDatagrid-tableWrapper': {
            overflowX: 'auto',
            margin: "1em",
          }
        }}
        {...rest}
      >
        {/* MAIN SCROLLABLE CONTENT */}
        <Box sx={{ 
            flex: 1, 
            minHeight: 0, // allow shrinking to fit the viewport
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <BreadCrump />
          <Box sx={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'auto',
          }}>
            {children}
          </Box>
        </Box>
        <Card 
          sx={{
            position: 'fixed',
            right: 0, 
            bottom: 0, 
            left: 0, 
            zIndex: 1010,
          }}>
          <Footer/>
        </Card>   
      </Layout>
      </IncidentCenterProvider>
      </BackgroundJobCenterProvider>
    </SystemStatusProvider>

  )
}

export default MyLayout
