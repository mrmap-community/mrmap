import { ReactNode } from 'react';
import { AppBar } from 'react-admin';

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
      {/** dummy div to push toolbar to the right. Searchfield will be placed here as soon as possible */}
      <div style={{width: '100%'}}/>
      

    </AppBar>
  )}








export default CustomAppBar;
