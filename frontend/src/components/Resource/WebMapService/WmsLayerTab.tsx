import { useCallback, useMemo } from 'react';
import { RaRecord, useNotify, useShowContext } from 'react-admin';

import { Container, Grid } from '@mui/material';

import EditGuesser from '../../../jsonapi/components/EditGuesser';
import WmsTreeView from './WmsTreeView';
import useSelectedLayer from './useSelectedLayer';


export const WmsLayers = () => {

  const { refetch } = useShowContext();
  const notify = useNotify(); 

  const [selectedLayer] = useSelectedLayer();


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
      if (selectedLayer !== null) {
          return <EditGuesser
              id={selectedLayer}
              resource='Layer'
              redirect={false}
              mutationOptions={{ meta: { type: "Layer" }, onSuccess}}
              
          />
      }
      return <Container>Select a layer to edit it</Container>
          
  }, [selectedLayer])
    
  return (
    <Grid container spacing={2} sx={{ justifyContent: 'space-between' }} >
        <Grid size={2}>
            <WmsTreeView />          
        </Grid>
        <Grid size={10}>
            {rightContent}
        </Grid>
    </Grid>
  )
}



export default WmsLayers