import { ReactNode } from 'react';
import { AppBar, TitlePortal } from 'react-admin';

import { Theme, useMediaQuery } from '@mui/material';

import AppBarToolbar from './AppBarToolbar';
import Logo from './Logo';

const CustomAppBar = (): ReactNode => { 
  const isLargeEnough = useMediaQuery<Theme>(theme =>
    theme.breakpoints.up('sm')
);
  return (
    <AppBar  
      position="sticky"
      toolbar={<AppBarToolbar />} 
    >
      {isLargeEnough && <Logo />}
      <TitlePortal/>
      

    </AppBar>
  )}








export default CustomAppBar;
