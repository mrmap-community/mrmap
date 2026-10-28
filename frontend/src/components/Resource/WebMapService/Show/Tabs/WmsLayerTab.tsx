import { useCallback, useMemo } from 'react';
import { RaRecord, RecordContextProvider, useGetMany, useNotify, useRecordContext } from 'react-admin';

import { Container, Grid, Stack } from '@mui/material';

import EditGuesser from '../../../../../jsonapi/components/EditGuesser';
import { useQueryParam } from '../../../../utils';
import ElementHistory from '../../../Generic/ServiceShow/ElementHistory';
import ElementInspection from '../../../Generic/ServiceShow/ElementInspection';
import WmsViewerButtons from '../../Button/ListActions';
import WmsTreeView from '../../TreeView/WmsTreeView';


export const WmsLayers = () => {

  const record = useRecordContext();

    const meta = useMemo(()=>{
        const jsonApiParams: Record<string, string> = {

        }
        const _meta = {
            jsonApiParams: jsonApiParams,
            relatedResource: {
                resource: "WebMapService",
                id: record?.id
            }
        }
        jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation,is_active,is_searchable'
        return _meta
    },[])


  const {data, refetch} = useGetMany("Layer", {ids:record?.layers.map((layer: RaRecord) => layer.id), meta: meta});

  const notify = useNotify(); 
  const [selectedLayer] = useQueryParam('selectedLayer');

    const wmsRecord = useMemo<RaRecord>(()=> ({
    ...record,
    id: record?.id || 1,
    layers: data
    }), [record, data])

  const onSuccess = useCallback(()=>{
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
      const inspection = <ElementInspection
          resource='Layer'
          id={selectedLayer ?? undefined}
          serviceResource='WebMapService'
          serviceId={record?.id}
          viewerActions={(layer) => (
              // the buttons read their service from the record context, so the record they open is
              // named here rather than taken from whatever screen renders this tab
              <RecordContextProvider value={record}>
                  <WmsViewerButtons
                      key={String(layer?.id)}
                      element={layer}
                      size='small'
                  />
              </RecordContextProvider>
          )}
          history={(layer) => <ElementHistory resource='Layer' record={layer}/>}
      />
      if (selectedLayer !== null && selectedLayer !== undefined) {
            return <Stack spacing={2}>
              {inspection}
              <EditGuesser
                id={selectedLayer}
                resource='Layer'
                redirect={false}
                mutationOptions={{ meta: { type: "Layer" }, onSuccess}}

            />
            </Stack>
      }
      return <Container>{inspection}</Container>
  }, [selectedLayer])
    
  return (
    <Grid container spacing={2} sx={{ justifyContent: 'space-between' }} >
        <Grid size={{ xs: 12, md: 3 }}>
            <WmsTreeView record={wmsRecord}/>          
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
            {rightContent}
        </Grid>
    </Grid>
  )
}



export default WmsLayers