import { DateField, EditButton, NumberField, RaRecord, RecordRepresentation, Show, SimpleShowLayout, SimpleShowLayoutProps, TextField, TopToolbar, useGetOne, useRecordContext } from 'react-admin';

import { useCallback, useMemo } from 'react';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';
import WmsTreeView from '../WebMapService/WmsTreeView';


const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);


const LayerMappingsForm = () => {
    const  contextRecord  = useRecordContext();

    const updateCandidateId = contextRecord?.updateCandidate?.id;
    const { data: updateCandidate, isPending,  } = useGetOne(
        'WebMapService',
        { id: updateCandidateId , meta: { jsonApiParams: { include: 'layers' } } },
    );
    const mappings = useMemo(() => contextRecord?.mappings || [], [contextRecord?.mappings])
    
    const getLayerProps = useCallback((record: RaRecord) => {
        const isConfirmed = mappings?.some(
            (mapping: RaRecord) =>
                mapping?.newLayer?.id === record.id &&
                mapping?.isConfirmed === true
        );

        return {
            itemId: record.id.toString(),
            label: (
                <span style={{ color: isConfirmed ? 'green' : 'red' }}>
                    <RecordRepresentation record={record}/>
                    {record.id}
                </span>
            )
        };
    }, [mappings])
    
    if (isPending) return <div>Loading...</div>
    
    return (
        <WmsTreeView
            record={updateCandidate}
            getLayerProps={getLayerProps}
        />
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
