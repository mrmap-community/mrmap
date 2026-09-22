import { useCallback, useMemo } from 'react';
import { RaRecord, useGetMany, useNotify, useRecordContext } from 'react-admin';

import { Container, Grid } from '@mui/material';
import EditGuesser from '../../../../../jsonapi/components/EditGuesser';
import { useQueryParam } from '../../../../utils';
import WmsTreeView from '../../TreeView/WmsTreeView';


export const WmsLayers = () => {


    const meta = useMemo(()=>{
        const jsonApiParams: any = {}
        const _meta = {
            jsonApiParams: jsonApiParams
        }
        jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation,is_active,is_searchable'
        return _meta
    },[])
  const record = useRecordContext();
  const {data, refetch} = useGetMany("Layer", {ids:record?.layers.map((layer: RaRecord) => layer.id), meta: meta});

  const notify = useNotify(); 
  const [selectedLayer] = useQueryParam('selectedLayer');

    const wmsRecord = useMemo<RaRecord>(()=> ({
    ...record,
    id: record.id,
    layers: data
    }), [record, data])

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
      if (selectedLayer !== null && selectedLayer !== undefined) {
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
            <WmsTreeView record={wmsRecord}/>          
        </Grid>
        <Grid size={10}>
            {rightContent}
        </Grid>
    </Grid>
  )
}



export default WmsLayers