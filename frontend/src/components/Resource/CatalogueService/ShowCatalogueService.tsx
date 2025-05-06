import { CardContent, CardHeader } from '@mui/material';
import { List, SelectField, Show, ShowViewProps, SimpleList, SimpleShowLayout, TextField } from 'react-admin';
import { useParams } from 'react-router-dom';
import AsideCard from '../../Layout/AsideCard';


export interface ShowCatalogueServiceProps extends Partial<ShowViewProps> {

}

const LastHarvestingJobs = ({}) => {
  const { id } = useParams()

  return (
    <AsideCard>
       <CardHeader 
        title="Last harvesting jobs"        
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
  
    return (
      <Show
        aside={<LastHarvestingJobs/>}
      >
        <SimpleShowLayout>
            <TextField source="id" />
            <TextField source="title" />
            <TextField source="abstract" />
        </SimpleShowLayout>
    </Show>
    )
};


export default ShowCatalogueService;