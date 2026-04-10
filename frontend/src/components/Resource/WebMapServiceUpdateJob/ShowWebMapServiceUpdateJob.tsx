import { DateField, EditButton, NumberField, Show, SimpleShowLayout, SimpleShowLayoutProps, TextField, TopToolbar, useGetList, useRecordContext } from 'react-admin';

import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';

const WmsShowActions = () => (
    <TopToolbar>
        <EditButton/>
    </TopToolbar>
);


const LayerMappingsForm = () => {
const  record  = useRecordContext();
  const { total, data } = useGetList(
    "LayerMapping",
    {
        pagination: { page: 1, perPage:1 },
        meta: {
          relatedResource:{
            resource: 'WebMapServiceUpdateJob',
            id: record?.id,
          },
        }
        
    }
  );
  console.log('total layer mappings', total)

  return (<>total: {total}</>)
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
    return (
        <Show 
            //queryOptions={{meta: meta}}
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
