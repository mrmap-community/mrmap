import { ReactNode } from 'react';
import { AppBar } from 'react-admin';

import { Theme, useMediaQuery } from '@mui/material';

import SearchInput from '../Search/SearchForm';
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
      <SearchInput/>
      

    </AppBar>
  )}








export default CustomAppBar;
