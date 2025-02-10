import { type ReactNode } from 'react';
import { CreateButton, useRecordContext } from 'react-admin';

import AgricultureIcon from '@mui/icons-material/Agriculture';

import ListGuesser from '../../../jsonapi/components/ListGuesser';

const HarvestButton = (): ReactNode => {
  const record = useRecordContext()
  
  return (
    <CreateButton
      resource='HarvestingJob'  
      icon={<AgricultureIcon />}
      label={"Harvest"}
      state={{ record: { service: record, harvestDatasets: true, harvestServices: true, stepSize: 500}}}
    />
      
  )
}

const CatalogueServiceList = (): ReactNode => {
  return (
    <ListGuesser
      resource='CatalogueService'
      additionalActions={<HarvestButton />}
    // aside={<TaskList />}
    />

  )
}

export default CatalogueServiceList
