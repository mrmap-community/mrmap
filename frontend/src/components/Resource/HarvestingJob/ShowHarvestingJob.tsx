import { CardHeader, Chip, Typography } from '@mui/material';
import { snakeCase } from 'lodash';
import { useCallback, useMemo } from 'react';
import { BooleanField, DateField, Identifier, Loading, NumberField, Show, TabbedShowLayout, useCreatePath, useRecordContext, useResourceDefinition, useShowContext } from 'react-admin';
import { useParams } from 'react-router-dom';
import { Count } from '../../../jsonapi/components/Count';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import useSparseFieldsForOperation from '../../../jsonapi/hooks/useSparseFieldsForOperation';
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
  const { error, isPending, record } = useShowContext();
  const name = 'HarvestingJob'
  const createPath = useCreatePath();
  const { id } = useParams()

  const getTabParams = useCallback((resource:string, relatedResource: string, relatedResourceId: Identifier, title: string, withCount: boolean = true)=>{
    return {
      label: <Typography component='span'>{title} {withCount ? <Chip size='small' label={<Count relatedResource={resource} relatedResourceId={relatedResourceId} resource={relatedResource}/>}/>: null}</Typography>,
      path: relatedResource,
      to: {
        pathname: createPath({
          resource: name,
          type: "show",
          id: record?.id || id
        }) + `/${relatedResource}`
      },
    }
  },[createPath, record, id, name])

  const getNestedListTab = useCallback((
    resource:string, 
    relatedResource: string, 
    relatedResourceId: Identifier, 
    title: string, 
    defaultSelectedColumns?: string[] ,
    withCount: boolean = true,
  )=>{
    return <TabbedShowLayout.Tab
    {...getTabParams(resource, relatedResource, relatedResourceId, title, withCount)}
   >
     <ListGuesser
       relatedResource={resource}
       relatedResourceId={relatedResourceId}
       resource={relatedResource}
       storeKey={false}
       {...defaultSelectedColumns && {defaultSelectedColumns: defaultSelectedColumns}}
     />
   </TabbedShowLayout.Tab>
  },[])
  if (isPending || record === undefined){
    return <Loading/>
  }
  return (
      <TabbedShowLayout>
        <TabbedShowLayout.Tab label="summary">
          <JsonApiReferenceField source="service" reference="CatalogueService" label="Service" />
          <BooleanField source="harvestDatasets"/>
          <BooleanField source="harvestServices"/>
          <NumberField source="totalRecords"/>
          <DateField source="backgroundProcess.dateCreated" showTime emptyText='-'/>
          <DateField source="backgroundProcess.doneAt" showTime emptyText='-'/>
          <ProgressField source="backgroundProcess.progress"/>
        </TabbedShowLayout.Tab>
        {getNestedListTab(name, 'HarvestedDatasetMetadataRelation', record?.id, 'Datasets', ['datasetMetadataRecord'], true)}
        {getNestedListTab(name,'HarvestedServiceMetadataRelation', record?.id, 'Services', ['serviceMetadataRecord'], true)}
        {getNestedListTab('BackgroundProcess', 'BackgroundProcessLog', record?.id, 'Logs', undefined, true)}
        {getNestedListTab('BackgroundProcess', 'TaskResult', record?.backgroundProcess?.id, 'Task Results', undefined,true)}
      </TabbedShowLayout>
  )
}

const AsideCardHarvestingJob = () => {
  const record = useRecordContext();

  return (
    <AsideCard>
      <CardHeader
        title='Record Overview'
        subheader={`${record?.totalRecords ?? 0} Records`}
      />

      <HarvestResultPieChart/>
    </AsideCard>
  )
}

const ShowHarvestingJob = () => {
    const { name } = useResourceDefinition()
    const { sparseFields: harvestingJobSparseFields } = useSparseFieldsForOperation(`list_${name}`)
    const { sparseFields: backgroundProcessSparseFields } = useSparseFieldsForOperation(`list_BackgroundProcess`)
    
    const sparseFields = useMemo(()=> {
      // see issue in drf-spectacular-json-api: https://github.com/jokiefer/drf-spectacular-json-api/issues/30
      // Therefore we need to implement this workaround to get all possible sparefield values
      return {
        ...harvestingJobSparseFields,
        ...backgroundProcessSparseFields,
      }
    }, [harvestingJobSparseFields, backgroundProcessSparseFields])

    const excludeSparseFields: any = useMemo(()=>({
      "HarvestingJob": [
        "temporaryMdMetadataFiles",
        "harvestedDatasetMetadata",
        "harvestedServiceMetadata",
      ],
      "BackgroundProcess": [
        "threads",
        "logs"
      ],
    }),[])
   
    const sparseFieldsParams = useMemo(()=>{
      const _sparseFieldsParams: any = {}
      for (const [key, value] of Object.entries(sparseFields)) {
        if (key in excludeSparseFields){
          const excludeFields = excludeSparseFields[`${key}`]
          const filteredSparseFields = value.filter(fieldName => !excludeFields.includes(fieldName))
          // Hint: there is a bug in django json:api package where sparse fields parameter are not camelCase translated correctly.
          // For that we need to transform the values to snake case
          _sparseFieldsParams[`fields[${key}]`] = filteredSparseFields.map(field => snakeCase(field)).join(',')
        }
      }
      return _sparseFieldsParams
    },[sparseFields, excludeSparseFields ])

    return (
      <Show
        queryOptions={{
          meta: {
            jsonApiParams:{
              include: 'service,backgroundProcess',
              'fields[CatalogueService]': 'id',
              ...sparseFieldsParams

            },
          }
        }}
        aside={<AsideCardHarvestingJob />}
      >
        <HarvestingJobTabbedShowLayout />
      </Show>
    )
};

export default ShowHarvestingJob