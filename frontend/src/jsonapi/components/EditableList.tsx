import _ from 'lodash';
import { useCallback, useMemo, useState } from 'react';
import { Identifier, RaRecord, useListController, useResourceDefinition } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';


export interface EditableDatagridProps {
  resource: string
}


const EditableDatagrid = (
  { 
    resource
  }: EditableDatagridProps
) => {
  
  const definition = useResourceDefinition({resource: resource})

  const { data, page, total, setPage, isPending } = useListController({
    resource: resource,
    //sort: { field: 'published_at', order: 'DESC' },
    //perPage: 10,
  });

  const [editRows, setEditRows] = useState<Identifier[]>([])

  const showFields = useFieldsForOperation(definition.options?.editOperationName ?? '', true, false)
  const editFields = useFieldsForOperation(definition.options?.editOperationName ?? '')

  const onEditRowClicked = useCallback((record: RaRecord)=>{
    setEditRows(_.union(editRows, [record.id]))
  },[editRows, setEditRows])


  const isInEditMode = useCallback((record: RaRecord)=>editRows.find(id => id === record.id),[editRows])
  

  const rows = useMemo(()=> data.map((record: RaRecord) => ({
    id: record.id
  })), [data])

  const columns = useMemo(()=> editFields.map(fieldDefinition => ({
    field: fieldDefinition.props.source,
    headerName: fieldDefinition.props.label ?? fieldDefinition.props.source,
    // renderEditCell: (params: GridRenderEditCellParams) => (
    //   createElement(fieldDefinition.component, fieldDefinition.props)
    // ),
    editable: true,
  })), [editFields])

  return (
    
          <></>
  )
}

export default EditableDatagrid