import { TabList } from '@mui/lab';
import TabContext from '@mui/lab/TabContext/TabContext';
import TabPanel from '@mui/lab/TabPanel/TabPanel';
import { CardHeader, Tab } from '@mui/material';
import { useState } from 'react';
import { useRecordContext } from 'react-admin';
import AsideCard from '../../Layout/AsideCard';
import HarvestResultPieChart from './HarvestJobResultPieChart';
import HarvestingJobTimingCharts from './HarvestingJobTimingCharts';

const AsideCardHarvestingJob = () => {
  const record = useRecordContext();

  const [value, setValue] = useState('1');

  return (
    <AsideCard>
      <TabContext value={value}>
        <TabList
          onChange={(event, newValue)=>setValue(newValue)}
        >
          <Tab value="1" label="Overview" />
          <Tab value="2" label="Download timings" />
          <Tab value="3" label="Database timings" />
        </TabList>

        <TabPanel value="1" >
          <CardHeader
            title='Harvesting Overview'
            subheader={`${record?.totalRecords ?? 0} Records`}
          />
          <HarvestResultPieChart/>
        </TabPanel>

        <TabPanel value="2" >
          <CardHeader
            title='Download Time Overall'
          />
          <HarvestingJobTimingCharts selectedSerie='fetchRecordDurationSeries'/>
        </TabPanel>

        <TabPanel value="3" >
          <CardHeader
            title='Total time to handle all records'
          />
          <HarvestingJobTimingCharts selectedSerie='dbDurationTotalSeries'/>
        </TabPanel>
      </TabContext>
    </AsideCard>
  )
}

export default AsideCardHarvestingJob