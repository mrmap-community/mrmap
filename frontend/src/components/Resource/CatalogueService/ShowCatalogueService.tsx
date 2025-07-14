import MailIcon from '@mui/icons-material/Mail';
import NoteAddIcon from '@mui/icons-material/NoteAdd';
import { CardContent, CardHeader } from '@mui/material';
import Badge from '@mui/material/Badge';
import Stack from '@mui/material/Stack';
import { useCallback, useMemo } from 'react';
import { RecordRepresentation, Show, ShowViewProps, SimpleShowLayout, TextField, useResourceDefinition, useTranslate, WithRecord } from 'react-admin';
import { useParams } from 'react-router-dom';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import { createElementIfDefined } from '../../../utils';
import AsideCard from '../../Layout/AsideCard';
import EmptyList from '../../Lists/Empty';
import CircularProgressWithLabel from '../../MUI/CircularProgressWithLabel';
import SimpleCard from '../../MUI/SimpleCard';
import ListHarvestingJob from '../HarvestingJob/ListHarvestingJob';
import HarvestingDailyStatsChart from './HarvestingDailyStatsChart';


export interface ShowCatalogueServiceProps extends Partial<ShowViewProps> {

}


const HarvestingJobProgress = ({record}: any) => {
  const translate = useTranslate();
  
  const tooltip = useMemo(() => {
    switch(record.phase){
      case 0:
        return translate('resources.HarvestingJob.phase.pending');
      case 1:
        return translate('resources.HarvestingJob.phase.getTotalRecords');
      case 2:
        return translate('resources.HarvestingJob.phase.downloadRecords');
      case 3:
        return translate('resources.HarvestingJob.phase.recordsToDb');
      case 4:
        return translate('resources.HarvestingJob.phase.completed');
      case 5:
        return translate('resources.HarvestingJob.phase.aborted');
      case 4711:
        return translate('resources.HarvestingJob.phase.abort');
      default:
        return 'info';
    }
  },[record.phase])

  const color = useMemo(()=>{
    switch(record.phase){
      case 0:
        return 'secondary';
      case 4:
        return 'success';
      case 5:
        return 'error';
      default:
        return 'info';
    }
  },[record.phase])

  return(
    <CircularProgressWithLabel 
      value={record.progress} 
      color={color}
      tooltip={tooltip}
    />
  )
};

const LastHarvestingJobs = ({

}) => {
  const { id } = useParams()

  const getSecondaryText = useCallback((record: any) => {
    const newRecords = record.newDatasetMetadataCount ?? 0 + (record.newServiceMetadataCount ?? 0)

    return (
      <Stack spacing={2} direction="row">
        <Badge badgeContent={newRecords} color="secondary">
          <NoteAddIcon color="action" />
        </Badge>
        <Badge badgeContent={4} color="success">
          <MailIcon color="action" />
        </Badge>
      </Stack>
    )

  },[])

  return (
    <AsideCard>
       <CardHeader 
        title="Last Harvesting Jobs"        
      /> 
      <CardContent>
      <ListHarvestingJob/>
      </CardContent>
    </AsideCard>
  )
};


const ShowCatalogueService = ({
  
  ...rest
}: ShowCatalogueServiceProps) => {
  const { id } = useParams()
  const { name: cswName, icon: cswIcon } = useResourceDefinition({resource: 'CatalogueService'})
  const { name: HarvestingJobName, icon: HarvestingJobIcon } = useResourceDefinition({resource: 'HarvestingJob'})
  const { name: periodicHarvestingJobName, icon: periodicHarvestingJobIcon } = useResourceDefinition({resource: 'PeriodicHarvestingJob'})
  const translate = useTranslate();

  return (
    <Show>
      <SimpleCard
        title={<RecordRepresentation />} subheader={<WithRecord label="author" render={record => <span>Created {record.createdAt} · Updated {record.lastModifiedAt}</span>} />}
      >
        <SimpleCard
          title={<span>{createElementIfDefined(cswIcon)} {cswName}</span>}
        >
          <SimpleShowLayout>
            <TextField source="id" />
            <TextField source="title" />
            <TextField source="abstract" />
          </SimpleShowLayout>
          

        </SimpleCard>
        
        <SimpleCard
          title={<span>{createElementIfDefined(HarvestingJobIcon)} {HarvestingJobName}</span>}
        >
          <HarvestingDailyStatsChart resource='HarvestedMetadataRelation' filter={{'harvesting_job__service': id}} />
          <ListHarvestingJob/>
        </SimpleCard>
        <SimpleCard
          title={<span>{createElementIfDefined(periodicHarvestingJobIcon)} {periodicHarvestingJobName}</span>}
        >
          <ListGuesser
            resource='PeriodicHarvestingJob'
            relatedResource='CatalogueService'
            empty={<EmptyList defaultValue={{service: {id: id}}} />}
          />
        </SimpleCard>
      </SimpleCard>
     
              
    </Show>
  )
};


export default ShowCatalogueService;