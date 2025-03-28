import DoneAllIcon from '@mui/icons-material/DoneAll';
import PauseIcon from '@mui/icons-material/Pause';
import RemoveDoneIcon from '@mui/icons-material/RemoveDone';
import { Chip, CircularProgress, Typography } from '@mui/material';
import { ReactNode, useCallback, useMemo } from 'react';
import { BooleanField, DateField, Identifier, Loading, NumberField, TabbedShowLayout, TextField, useCreatePath, useShowContext } from 'react-admin';
import { useParams } from 'react-router-dom';
import { Count } from '../../../jsonapi/components/Count';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import ProgressField from '../../Field/ProgressField';

const renderStatus = (status: string): ReactNode => {
  switch(status){
    case 'aborted':
      return <Typography component='span'><RemoveDoneIcon/> aborted </Typography>
       
    case 'completed':
      return <Typography component='span'><DoneAllIcon/> completed </Typography>
    case 'running':
      return <Typography component='span'><CircularProgress/> running </Typography>
    case 'pending':
      return <Typography component='span'><PauseIcon/> pending </Typography>
    default:
      return <PauseIcon />
  }
}

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

  const tabs = useMemo(()=>{
    return[
      getNestedListTab(name, 'HarvestedDatasetMetadataRelation', record?.id, 'Datasets', ['datasetMetadataRecord'], true),
      getNestedListTab(name,'HarvestedServiceMetadataRelation', record?.id, 'Services', ['serviceMetadataRecord'], true),
      getNestedListTab('BackgroundProcess', 'BackgroundProcessLog', record?.backgroundProcess?.id, 'Logs', undefined, true),
      getNestedListTab(name, 'TemporaryMdMetadataFile', record?.id, 'Unhandled Records', undefined, true),

      //getNestedListTab('BackgroundProcess', 'TaskResult', record?.backgroundProcess?.id, 'Task Results', undefined,true)
    ]
  },[record])

  const progressColor = useMemo(()=>{
    switch(record?.backgroundProcess.status) {
      case 'aborted':
        return 'warning'
      case 'completed':
        return 'success'
      default:
        return 'info'
    }
  },[record?.backgroundProcess])


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
          {/**<FunctionField source="backgroundProcess.status" render={record => renderStatus(record?.backgroundProcess?.status)}/>*/}
          <TextField source="backgroundProcess.phase"/>
          <NumberField source="totalSteps"/>
          <NumberField source="doneSteps"/>
          <ProgressField source="progress" color={progressColor}/>
        </TabbedShowLayout.Tab>
        {...tabs}
      </TabbedShowLayout>
  )
}


export default HarvestingJobTabbedShowLayout