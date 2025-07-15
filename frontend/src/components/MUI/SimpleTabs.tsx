import Box from '@mui/material/Box';
import Tab, { TabProps } from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import * as React from 'react';
import { SyntheticEvent, useState } from 'react';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const CustomTabPanel = (props: TabPanelProps) => {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const a11yProps = (index: number) => {
  return {
    id: `simple-tab-${index}`,
    'aria-controls': `simple-tabpanel-${index}`,
    
  };
}

export interface SimpleTabsProps {
  tabs: TabProps[]
}

const SimpleTabs = ({
  tabs
}: SimpleTabsProps) => {
  const [value, setValue] = useState(0);

  const handleChange = (event: SyntheticEvent, newValue: number) => {
    setValue(newValue);
  };

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={value} onChange={handleChange}>
          {tabs.map((tab, index)=> <Tab {...tab} {...a11yProps(index)}/>)}
        </Tabs>
      </Box>
      {tabs.map((tab, index) => <CustomTabPanel value={value} index={index} key={`simple-tab-${index}`}>{tab.children}</CustomTabPanel>)}
    </Box>
  );
}

export default SimpleTabs;