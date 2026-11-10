import { type ReactNode } from 'react';
import { Layout, useSidebarState, type LayoutProps } from 'react-admin';

import { Box, Card } from '@mui/material';

import { SystemStatusProvider } from '../../context/SystemStatusContext';
import I18Observer from '../../jsonapi/components/I18Observer';
import RealtimeBus from '../../jsonapi/components/Realtime/RealtimeBus';
import MrMapAppBar from './AppBar';
import BreadCrump from './BreadCrump';
import Footer from './Footer';
import CustomMenu from './Menu';


const MyLayout = (
  {
    children,
    ...rest
  }: LayoutProps
): ReactNode => {
  const [open] = useSidebarState()


  return (
    <SystemStatusProvider>
      <RealtimeBus/> 
      <I18Observer/>
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
            overfloxX: 'hidden',
            marginLeft: "1em",
            marginRight: "1em",
            marginBottom: "1em",
          },
          '& .RaShow-main': {
            width: `calc('100vw' - ${open ? '240px' : '50px'}  - 3em)`,
            //maxHeight: 'calc(50vh - 174px )', // 174px ==> 50 appbar, 52 pagination, 64 table actions, 8 top padding
            overfloxX: 'hidden',
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
          style={{
            position: 'fixed',
            right: 0, 
            bottom: 0, 
            left: 0, 
            zIndex: 1010,
          }}>
          <Footer/>
        </Card>   
      </Layout>
    </SystemStatusProvider>

  )
}

export default MyLayout
