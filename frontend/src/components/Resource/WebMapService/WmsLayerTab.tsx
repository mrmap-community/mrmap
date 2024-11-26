import { useCallback, useMemo } from 'react';
import { RaRecord, useNotify, useShowContext } from 'react-admin';

import { Grid } from '@mui/material';

import { useParams } from 'react-router-dom';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import WmsTreeView from './WmsTreeView';


export const WmsLayers = () => {
    
  const { layerId } = useParams();
      
  const { refetch } = useShowContext();
  const notify = useNotify(); 


  const onSuccess = useCallback((record: RaRecord)=>{
      notify(
          'ra.notification.updated', 
          {
              messageArgs: { smart_count: 1 },
              undoable: false,
              type: 'success',
          }
  );
      // refetch the wms if the update was successfully
      refetch()
  },[notify, refetch])

  


  const rightContent = useMemo(()=> {
      if (layerId !== ':layerId') {
          return <EditGuesser
              id={layerId}
              resource='Layer'
              redirect={false}
              mutationOptions={{ meta: { type: "Layer" }, onSuccess}}
          />
      }
      return null
          
  }, [layerId])
    
  return (
      <Grid container spacing={2} sx={{ justifyContent: 'space-between' }} >
          <Grid item xs={4}>
              <WmsTreeView />          
          </Grid>
          <Grid item xs={8}>
              {rightContent}
          </Grid>
      </Grid>
  )
}



export default WmsLayers