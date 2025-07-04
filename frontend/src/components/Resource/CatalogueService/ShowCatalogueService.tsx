import { CardContent, CardHeader } from '@mui/material';
import { List, SelectField, Show, ShowViewProps, SimpleList, TabbedShowLayout, TextField, useResourceDefinition } from 'react-admin';
import { useParams } from 'react-router-dom';
import ConfigureRelatedResource from '../../../jsonapi/components/ConfigureRelatedResource';
import { createElementIfDefined } from '../../../utils';
import AsideCard from '../../Layout/AsideCard';


export interface ShowCatalogueServiceProps extends Partial<ShowViewProps> {

}

const LastHarvestingJobs = ({}) => {
  const { id } = useParams()

  return (
    <AsideCard>
       <CardHeader 
        title="Last Harvesting Jobs"        
      /> 
      <CardContent>
      <List
        resource='HarvestingJob'
        sort={{field: "dateCreated", order: "DESC"}}
        queryOptions={{
          meta: {
            relatedResource: {
              resource: 'CatalogueService',
              id: id
            },
            
          },
          
        }}
        
      >
        <SimpleList
          primaryText={record => record.title}
          secondaryText={record => <SelectField record={record} source='phase'/>}
          tertiaryText={record => new Date(record.dateCreated).toUTCString()}
          rowClick={"show"}
          rowSx={record => ({ backgroundColor: record.nb_views >= 500 ? '#efe' : 'white' })}
        />
      </List>
      </CardContent>
    </AsideCard>
  )
};


const ShowCatalogueService = ({
  
  ...rest
}: ShowCatalogueServiceProps) => {
  
  const { name: cswName, icon: cswIcon } = useResourceDefinition({resource: 'CatalogueService'})
  const { name: periodicHarvestingJobName, icon: periodicHarvestingJobIcon } = useResourceDefinition({resource: 'PeriodicHarvestingJob'})

  return (
    <Show
      aside={<LastHarvestingJobs/>}
    >
      <TabbedShowLayout>
        <TabbedShowLayout.Tab label={cswName} icon={createElementIfDefined(cswIcon)}>
          
            <TextField source="id" />
            <TextField source="title" />
            <TextField source="abstract" />

        </TabbedShowLayout.Tab>
        
        <TabbedShowLayout.Tab label={periodicHarvestingJobName} icon={createElementIfDefined(periodicHarvestingJobIcon)}>
            <ConfigureRelatedResource relatedResource='PeriodicHarvestingJob' relatedName='periodicHarvestingJobs'/>
        </TabbedShowLayout.Tab>


        
      </TabbedShowLayout>
        
    </Show>
  )
};


export default ShowCatalogueService;