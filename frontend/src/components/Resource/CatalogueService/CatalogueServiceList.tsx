import { PlayArrow } from '@mui/icons-material';
import AgricultureIcon from '@mui/icons-material/Agriculture';
import { type ReactNode } from 'react';
import { CreateButton, Identifier, ShowButton, useRecordContext } from 'react-admin';
import ListWithDialogs from '../../../jsonapi/components/ListWithDialogs';


export interface ShowRunningHarvestingJobButtonProps {
  id: Identifier
}

const ShowRunningHarvestingJobButton = ({id}: ShowRunningHarvestingJobButtonProps): ReactNode => {
  return (
    <ShowButton
      resource='HarvestingJob'
      record={{id: id}}
      label='running job'
      icon={<PlayArrow/>}
    />
  )
}


const HarvestButton = (): ReactNode => {
  const record = useRecordContext()
  
  if (record?.runningHarvestingJob !== undefined){
    return (
      <ShowRunningHarvestingJobButton
        id={record.runningHarvestingJob.id}
      />
    )
    
  } else {
      return (
      <CreateButton
        resource='HarvestingJob'  
        icon={<AgricultureIcon />}
        label={"Harvest"}
        state={{ record: { service: record, harvestDatasets: true, harvestServices: true, stepSize: 500}}}
      />
    )
  }
}

const CatalogueServiceList = (): ReactNode => {
  return (
    <ListWithDialogs
      listGuesserProps={
        {
          additionalActions: <HarvestButton />
        }
      }
    />
  )
}

export default CatalogueServiceList
