import { EditButton, Identifier, RaRecord, RecordRepresentation, Show, SimpleShowLayoutProps, useGetOne, useRecordContext, WrapperField } from 'react-admin';

import { useCallback, useMemo, useState } from 'react';
import WmsTreeView from '../WebMapService/WmsTreeView';

import { Box, Drawer, Stack } from '@mui/material';
import ListGuesser, { ListGuesserProps } from '../../../jsonapi/components/ListGuesser';
import SimpleCard from '../../MUI/SimpleCard';
import { useQueryParam } from '../../utils';
import { EditLayerMapping } from './EditLayerMapping';

type DiffStatus = 'added' | 'removed' | 'unchanged' | 'modified';



const DiffWmsLayerTree = () => {
    const  contextRecord  = useRecordContext();

    const queryOptionsMeta = useMemo(() => {
        const meta: any ={  
            jsonApiParams: { 
                include: 'layers',
            } 
        }
        meta.jsonApiParams['fields[Layer]'] = 'mptt_lft,mptt_rgt,mptt_depth,title,string_representation,identifier'
        meta.jsonApiParams['fields[WebMapService]'] = 'title,layers'
        return meta;
    }, [])

    const { data: updateCandidate, isPending: updateCandidatePending,  } = useGetOne(
        'WebMapService',
        { 
            id: contextRecord?.updateCandidate?.id,
            meta: queryOptionsMeta
        },
    );
    const { data: currentServiceState, isPending: currentServiceStatePending,  } = useGetOne(
        'WebMapService',
        { 
            id: contextRecord?.service?.id , 
            meta: queryOptionsMeta 
        },
    );

    /**
     * updateCandidate.layers is a list of RaRecords which have mpttLft mpttRgt mpttLevel mpttTree values
     * currentServiceState.layers is a list of RaRecords which have mpttLft mpttRgt mpttLevel mpttTree values
     * TODO: how to merge both tree's to one, so we can show also deleted layers
     */

    const newLayers = useMemo(() => updateCandidate?.layers || [], [updateCandidate?.layers])
    const oldLayers = useMemo(() => currentServiceState?.layers || [], [currentServiceState?.layers])
    const deleted = useMemo(()=>(oldLayers.filter(
        (old: RaRecord) => !newLayers.some((node: RaRecord) => node.identifier === old.identifier)
    )),[newLayers, oldLayers])



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
        <WmsTreeView
            record={updateCandidate}
            getLayerProps={getLayerProps}
            focusSelectedLayer={true}
        />
    )
}


const LayerMappingList = (
    props: ListGuesserProps
) => {
    const  contextRecord  = useRecordContext();

    return (
        <ListGuesser
            title="Layer Mappings"
            resource="LayerMapping"
            relatedResource="WebMapServiceUpdateJob"
            relatedResourceId={contextRecord?.id}
            filterDefaultValues={{'isConfirmed': false}}
            disableSyncWithLocation
            defaultSelectedColumns={['id', 'oldLayer', 'newLayer', 'isConfirmed']}
            {...props}
        />
    )
}

const WebMapServiceUpdateJobCard = ()=>{
    const [selectedLayer, setSelectedLayer] = useQueryParam('selectedLayer');
    const contextRecord = useRecordContext();

    const title = useMemo(() => {
    const serviceTitle = contextRecord?.service?.stringRepresentation || 'unknown service';
        return `Update Job (${contextRecord?.id}) for ${serviceTitle}`
    }, [contextRecord?.service])

    const [isOpen, setIsOpen] = useState(false);
    const rowActions = useMemo(() => {
        return (
            <WrapperField label="Actions" >
                <EditButton onClick={() => setIsOpen(true)} />
            </WrapperField >
        )
    },[])

    return(
         <SimpleCard
            title={title}
            subheader={'the updateprocess will automatically continue once all issues are resolved.'}
        >
            <Stack direction="row" >

                {/* LEFT: TREE */}
                <Box sx={{ width: 320, borderRight: '1px solid #ddd', }}>
                    <SimpleCard
                        title={`New Web Map Service Layer Structure`}
                        subheader={'click on a layer to see details and edit the mapping in the right panel'}
                        cardProps={{
                            sx: {boxShadow: 0, height: '100%', border: 'none', marginRight: 2}
                        }}
                    >
                        <DiffWmsLayerTree />
                    </SimpleCard>
                </Box>

                {/* RIGHT: TABLE */}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                    <SimpleCard
                        title={`List of issues to be resolved`}
                        subheader={`Click on the edit button to confirm or reject a layer mapping change.`}
                        cardProps={{
                            sx: {boxShadow: 0, height: '100%', border: 'none', marginRight: 2}
                        }}
                    >
                    <LayerMappingList
                        onRowClick={(record) => {
                            setSelectedLayer(record?.newLayer?.id?.toString());
                        }}
                        rowActions={rowActions}
                    />
                    </SimpleCard>
                </Box>

                {/* DETAIL PANEL */}
                <Drawer
                    anchor="right"
                    open={isOpen}
                    onClose={() => setIsOpen(false)}

                >
                    <SimpleCard
                        title={`Edit Layer Mapping for ${selectedLayer || 'unknown layer'}`}
                    >
                        <EditLayerMapping />
                    </SimpleCard>
                </Drawer>

            </Stack>
        </SimpleCard>
    )
}

export const ShowWebMapServiceUpdate = (props: SimpleShowLayoutProps) => {
    
    const meta = useMemo(()=>(
         {
            jsonApiParams: {
                include: 'service,mappings'
            }
        } 
    ),[])

    return (
        <Show 
            queryOptions={{meta: meta}}
            actions={<></>}
            
        >
           <WebMapServiceUpdateJobCard/>

        </Show>
    )
};
