import PlayArrow from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import { useEffect, useMemo } from 'react';
import { Button, PrevNextButtons, TopToolbar, useCreate, useGetList, useRecordContext, useRedirect, useResourceDefinition, useUpdate } from 'react-admin';


const JsonApiPrevNextButtons = () => {
  const { name } = useResourceDefinition()

  const jsonApiParams = useMemo(()=>{
    const params: any = {}
    params[`fields[${name}]`] = 'id'
    return params
  },[name])

  return (
    <PrevNextButtons
      queryOptions={{ 
        meta: {
          jsonApiParams: jsonApiParams,
        }
      }}
      linkType='show'
      limit={10}
      sort={{field:'id', order:'DESC'}}
    />
  )
}


const AbortButton = () => {
  const record = useRecordContext();
  const params = useMemo(() => ({
    id: record?.backgroundProcess?.id,
    data: {
      phase: 'abort'
    },
    previousData: record?.backgroundProcess  
  }),[record])

  const [update, { isPending }] = useUpdate();

  return (
    <Button 
      //disabled={['aborted', 'completed'].includes(record?.backgroundProcess?.status)} 
      variant="outlined" 
      color="warning" 
      startIcon={<StopIcon />} 
      label='stop' 
      loading={isPending} 
      onClick={() => update("BackgroundProcess", params)}
    />
  )
}


const StartAgainButton = () => {
  const record = useRecordContext();
  const params = useMemo(() => ({
    data: {
      harvestDatasets: true,
      harvestServices: true,
      stepSize: 50,
      service: {
        id: record?.service?.id
      }
    },
  }),[record])

  const { total: totalRunningJobs } = useGetList(
    "HarvestingJob",
    {
        pagination: { page: 1, perPage:1 },
        filter: {
          'service.id': record?.service?.id,
          'isUnready': true
        },
        meta: {
          jsonApiParams:{
            'fields[HarvestingJob]': 'id',
          },
        }
        
    }
  );
  const [create, { data, isPending, isSuccess }] = useCreate();
  const redirect = useRedirect();


  useEffect(()=>{
    if (isSuccess){
      redirect("show", "HarvestingJob", data.id)
    }
  },[isSuccess])

  return (
    <Button 
      disabled={(totalRunningJobs ?? 0 ) > 0} 
      variant="outlined" 
      color="primary" 
      startIcon={<PlayArrow />} 
      label='start again' 
      loading={isPending} 
      onClick={() => create("HarvestingJob", params)}
    />
  )
}


const HarvestingJobActions = () => {
  return (
    <TopToolbar>
      <StartAgainButton/>
      <AbortButton/>
      <JsonApiPrevNextButtons/>
    </TopToolbar>
  )
}

export default HarvestingJobActions