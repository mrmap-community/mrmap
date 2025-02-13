import { BooleanField, NumberField, Show, TabbedShowLayout, useRecordContext } from 'react-admin';
import JsonApiReferenceManyCount from '../../../jsonapi/components/JsonApiReferenceManyCountField';
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
          <JsonApiReferenceManyCount source="newDatasetRecords"/>

        </TabbedShowLayout.Tab>

        <TabbedShowLayout.Tab label="New Datasets" path="new-datasets">
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'harvested_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab label="Existing Datasets" path="existing-datasets">
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'ignored_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab label="Updated Datasets" path="updated-datasets">
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'updated_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab label="Logs" path="logs">
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
        queryOptions={{meta: {jsonApiParams:{include: 'service'}}}}
      >
        <HarvestingJobTabbedShowLayout />       
      </Show>
    )
};

export default ShowHarvestingJob