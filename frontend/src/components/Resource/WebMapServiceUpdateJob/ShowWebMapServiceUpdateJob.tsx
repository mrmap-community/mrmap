import { DateField, EditButton, Identifier, NumberField, RaRecord, RecordRepresentation, Show, SimpleShowLayout, SimpleShowLayoutProps, TextField, TopToolbar, useGetOne, useRecordContext } from 'react-admin';

import { Card, Stack } from '@mui/material';
import { useCallback, useMemo } from 'react';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import WmsTreeView from '../WebMapService/WmsTreeView';
import useSelectedLayer from '../WebMapService/useSelectedLayer';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);

type DiffStatus = 'added' | 'removed' | 'unchanged' | 'modified';

const LayerMappingsForm = () => {
    const  contextRecord  = useRecordContext();
    const [selectedLayer] = useSelectedLayer();

    const { data: updateCandidate, isPending: updateCandidatePending,  } = useGetOne(
        'WebMapService',
        { id: contextRecord?.updateCandidate?.id, meta: { jsonApiParams: { include: 'layers' } } },
    );
    const { data: currentServiceState, isPending: currentServiceStatePending,  } = useGetOne(
        'WebMapService',
        { id: contextRecord?.service?.id , meta: { jsonApiParams: { include: 'layers' } } },
    );

    const newLayers = useMemo(() => updateCandidate?.layers || [], [updateCandidate?.layers])
    const oldLayers = useMemo(() => currentServiceState?.layers || [], [currentServiceState?.layers])
    const mappings = useMemo(() => contextRecord?.mappings || [], [contextRecord?.mappings])

    const selectedMapping = useMemo(() => 
        mappings.find((m: RaRecord) => m.newLayer?.id === selectedLayer),
        [mappings, selectedLayer]
    );

    const newLayer = newLayers.find((l: RaRecord) => l.id === selectedLayer);
    const oldLayer = selectedMapping?.oldLayer
    ? oldLayers.find((l: RaRecord) => l.id === selectedMapping.oldLayer.id)
    : null;

    console.log('Selected Mapping:', selectedMapping);

    const diffMap = useMemo(() => {
        const map = new Map<Identifier, DiffStatus>();

        const oldByIdentifier = new Map<Identifier, RaRecord>(
            oldLayers.map((l: RaRecord) => [l.identifier, l])
        );

        const newByIdentifier = new Map<Identifier, RaRecord>(
            newLayers.map((l: RaRecord) => [l.identifier, l])
        );

        // check new layers
        newLayers.forEach((newLayer: RaRecord) => {
            const key = newLayer.identifier;

            const oldLayer = oldByIdentifier.get(key);

            if (!oldLayer) {
                map.set(newLayer.id, 'added');
            } else {
                if (oldLayer.title !== newLayer.title) {
                    map.set(newLayer.id, 'modified');
                } else {
                    map.set(newLayer.id, 'unchanged');
                }
            }
        });

        // check removed layers
        oldLayers.forEach((oldLayer: RaRecord) => {
            const key = oldLayer.identifier;

            if (!newByIdentifier.has(key)) {
                map.set(oldLayer.id, 'removed');
            }
        });

        return map;
    }, [oldLayers, newLayers]);

    const getLayerProps = useCallback((record: RaRecord) => {
        
        const status = diffMap.get(record.id);

        let color = 'inherit';
        let prefix = '';

        switch (status) {
            case 'added':
                color = 'green';
                prefix = '➕ ';
                break;
            case 'removed':
                color = 'red';
                prefix = '❌ ';
                break;
            case 'modified':
                color = 'orange';
                prefix = '✏️ ';
                break;
        }
        return {
            itemId: record.id.toString(),
            label: (
                <span style={{ color }}>
                    {prefix}
                    <RecordRepresentation record={record}/>
                </span>
            )
        };
    }, [diffMap])
    
    if (updateCandidatePending || currentServiceStatePending) return <div>Loading...</div>
    
    return (
        <Stack
            sx={{
                marginLeft: '5px', 
                maxHeight: '80vh', 
                
                justifyContent: "space-between",
                alignItems: "stretch",
            }} 
            spacing={2}
        >
            <Card 
                sx={{
                    overflow: 'auto',
                    maxHeight: '30vh',
                }}
            > 
                <WmsTreeView
                    record={updateCandidate}
                    getLayerProps={getLayerProps}
                />
            </Card>
            <Card  >
               <EditGuesser
                    resource="LayerMapping"
                    id={selectedMapping?.id}
                    redirect={false}
               >

               </EditGuesser>
            </Card>
        </Stack>
    )
}

export const ShowWebMapServiceUpdate = (props: SimpleShowLayoutProps) => {
    
/*
   // const { name: layerName, icon: layerIcon } = useResourceDefinition({resource: 'Layer'})
    //const { name: wmsName, icon: wmsIcon } = useResourceDefinition({resource: 'WebMapService'})
    //const { name: operationUrlName, icon: operationUrlIcon } = useResourceDefinition({resource: 'WebMapServiceOperationUrl'})

    //const fieldDefinitions = useFieldsForOperation('partial_update_WebMapService', false, true);

    //const fields = useMemo(()=>(
    //    fieldDefinitions.filter(fieldDef => ['title', 'abstract'].includes(fieldDef.props.source)).map(fieldDef => createElement(fieldDef.component, fieldDef.props))
    //),[fieldDefinitions])


    //const meta = useMemo(()=>{
    /    const jsonApiParams: any = {
                include: 'layers,operationUrls',
            }
        const _meta = {
            jsonApiParams: jsonApiParams
        }
        jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation'
        return _meta
    },[])
*/
    const meta = useMemo(()=>(
         {jsonApiParams: {include: 'mappings'}} 
    ),[])

    return (
        <Show 
            queryOptions={{meta: meta}}
            actions={<WmsShowActions/>}
            aside={<div><LayerMappingsForm/></div>}             
        >
        <SimpleShowLayout>
            <TextField source="id" />
            <JsonApiReferenceField source="service" reference="WebMapService" label="Service" />
            <DateField source="dateCreated" />
            <DateField source="doneAt" />
            <NumberField source="status" />
        </SimpleShowLayout>
           
        </Show>
    )
};
