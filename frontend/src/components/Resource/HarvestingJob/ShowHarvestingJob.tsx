import { Chip, Typography } from '@mui/material';
import { BooleanField, NumberField, Show, TabbedShowLayout, useRecordContext } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import ProgressField from '../../Field/ProgressField';

const HarvestingJobTabbedShowLayout = () => {
  const record = useRecordContext();
  return (
      <TabbedShowLayout>

        <TabbedShowLayout.Tab label="summary">
          
          <JsonApiReferenceField source="service" reference="CatalogueService" label="Service" />
          <BooleanField source="harvestDatasets"/>
          <BooleanField source="harvestServices"/>
          <NumberField source="totalRecords"/>
          <ProgressField source="backgroundProcess.progress"/>
        </TabbedShowLayout.Tab>

        <TabbedShowLayout.Tab 
          label={<Typography>New Datasets <Chip label={record?.newDatasetRecords?.length || 0} color="success" size="small"/></Typography>} 
          path="new-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'harvested_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography>Existing Datasets <Chip label={record?.existingDatasetRecords?.length || 0} size="small"/></Typography>} 
          path="existing-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'ignored_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography>Updated Datasets <Chip label={record?.updatedDatasetRecords?.length || 0} size="small"/></Typography>} 
          path="updated-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'updated_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography>Logs <Chip label={record?.backgroundProcess?.logs?.length || 0} size="small"/></Typography>} 
          path="logs"
        >
          <ListGuesser
            relatedResource='BackgroundProcess'
            relatedResourceId={record?.backgroundProcess?.id}
            resource='BackgroundProcessLog'
          />
        </TabbedShowLayout.Tab>


      </TabbedShowLayout>
  )
}


const ShowHarvestingJob = () => { 
    return (
      <Show 
        queryOptions={{meta: {jsonApiParams:{include: 'service,backgroundProcess'}}}}
      >
        <HarvestingJobTabbedShowLayout />       
      </Show>
    )
};

export default ShowHarvestingJob