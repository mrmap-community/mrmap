import { CardHeader, Chip, Typography } from '@mui/material';
import { BooleanField, DateField, NumberField, Show, TabbedShowLayout, useRecordContext } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import ProgressField from '../../Field/ProgressField';
import AsideCard from '../../Layout/AsideCard';
import HarvestResultPieChart from './Charts';


const dateFormatRegex = /^\d{4}-\d{2}-\d{2}$/;
const dateParseRegex = /(\d{4})-(\d{2})-(\d{2})/;

const convertDateToString = (value: string | Date) => {
    // value is a `Date` object
    if (!(value instanceof Date) || isNaN(value.getDate())) return '';
    const pad = '00';
    const yyyy = value.getFullYear().toString();
    const MM = (value.getMonth() + 1).toString();
    const dd = value.getDate().toString();
    return `${yyyy}-${(pad + MM).slice(-2)}-${(pad + dd).slice(-2)}`;
};

const dateFormatter = (value: string | Date) => {
  // null, undefined and empty string values should not go through dateFormatter
  // otherwise, it returns undefined and will make the input an uncontrolled one.
  if (value == null || value === '') return '';
  if (value instanceof Date) return convertDateToString(value);
  // Valid dates should not be converted
  if (dateFormatRegex.test(value)) return value;

  return convertDateToString(new Date(value));
};

const HarvestingJobTabbedShowLayout = () => {
  const record = useRecordContext();
  return (
      <TabbedShowLayout>

        <TabbedShowLayout.Tab label="summary">
          <JsonApiReferenceField source="service" reference="CatalogueService" label="Service" />
          <BooleanField source="harvestDatasets"/>
          <BooleanField source="harvestServices"/>
          <NumberField source="totalRecords"/>
          <DateField source="backgroundProcess.dateCreated" showTime emptyText='unknown'/>
          <DateField source="backgroundProcess.doneAt" showTime emptyText='unknown'/>
          <ProgressField source="backgroundProcess.progress"/>
        </TabbedShowLayout.Tab>

        <TabbedShowLayout.Tab 
          label={<Typography component='span' variant='body2'>New Datasets <Chip label={record?.newDatasetRecords?.length || 0} color="success" size="small"/></Typography>} 
          path="new-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'harvested_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography component='span' variant='body2'>Existing Datasets <Chip label={record?.existingDatasetRecords?.length || 0} size="small"/></Typography>} 
          path="existing-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'ignored_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography component='span' variant='body2'>Updated Datasets <Chip label={record?.updatedDatasetRecords?.length || 0} size="small"/></Typography>} 
          path="updated-datasets"
        >
          <ListGuesser
            resource='DatasetMetadataRecord'
            filter={{'updated_by': record?.id}}
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography component='span' variant='body2'>Logs <Chip label={record?.backgroundProcess?.logs?.length || 0} size="small"/></Typography>} 
          path="logs"
        >
          <ListGuesser
            relatedResource='BackgroundProcess'
            relatedResourceId={record?.backgroundProcess?.id}
            resource='BackgroundProcessLog'
          />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab 
          label={<Typography component='span' variant='body2'>Task Results <Chip label={record?.backgroundProcess?.threads?.length || 0} size="small"/></Typography>} 
          path="tasks"
        >
          <ListGuesser
            relatedResource='BackgroundProcess'
            relatedResourceId={record?.backgroundProcess?.id}
            resource='TaskResult'
          />
        </TabbedShowLayout.Tab>


      </TabbedShowLayout>
  )
}


const ShowHarvestingJob = () => { 
    return (
      <Show
        queryOptions={{meta: {jsonApiParams:{include: 'service,backgroundProcess'}}}}
        aside={
          <AsideCard
            
          >
            <CardHeader
              title="Chart"
            />
            <HarvestResultPieChart/>
          </AsideCard>
        }
        
      >
        
      <HarvestingJobTabbedShowLayout />
      </Show>
    )
};

export default ShowHarvestingJob