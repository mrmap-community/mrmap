import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useMemo, useState } from 'react';
import { RaRecord, Show, TabbedShowLayout, TextField, useGetRecordRepresentation, useRecordContext } from 'react-admin';
import JsonApiReferenceField from '../../../jsonapi/components/ReferenceField';


const DatasetMetadataRecordTabbedShowLayout = () => {
  const record = useRecordContext();
  const getRecordRepresentation = useGetRecordRepresentation('DatasetMetadataRecord');

  const [edges, setEdges] = useState<Edge[]>([]);

  const nodes: Node[] = useMemo(()=>{
    const newEdges: Edge[] = []
    const relations = [
      ...(record?.harvestedThrough || []), 
      ...(record?.selfPointingLayers || []), 
      ...(record?.selfPointingFeatureTypes || []), 
    ].map((relation: RaRecord, index: number) => {
      const edge: Edge = {id: `e${relation.id}-${record?.id}`, source: String(relation.id) , target: String(record?.id) }
      newEdges.push(edge)
      return {
        id: String(relation.id),
        position: {x: index * 200, y: index * 200 + 200}, 
        data:{ label: relation.stringRepresentation}
      }
    }) || []

    setEdges(newEdges)

    return [
      ...(record ? [{id: String(record?.id), position: {x: 0, y: 0}, data:{ label: getRecordRepresentation(record)}}] : []),
      ...relations,
    ]
  },[record])


  return (
      <TabbedShowLayout>

        <TabbedShowLayout.Tab label="summary">
          
          <JsonApiReferenceField source="service" reference="CatalogueService" label="Service" />
          <TextField source="title"/>
        

        </TabbedShowLayout.Tab>

        <TabbedShowLayout.Tab label="Relations" path="relations">
        <div style={{ width: '100vw', height: '100vh' }}>
          <ReactFlow 
            nodes={nodes}
            fitView
            edges={edges}          
          >
            <Controls />
            <MiniMap />
            <Background variant="dots" gap={12} size={1} />
          </ReactFlow>
        </div>
        </TabbedShowLayout.Tab>


      </TabbedShowLayout>
  )
}


const ShowDatasetMetadataRecord = () => { 
    return (
      <Show 
        queryOptions={{meta: {jsonApiParams:{include: 'selfPointingLayers.service,selfPointingFeatureTypes.service,harvestedThrough'}}}}
      >
        <DatasetMetadataRecordTabbedShowLayout />       
      </Show>
    )
};

export default ShowDatasetMetadataRecord