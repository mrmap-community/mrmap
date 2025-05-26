import { useCallback, useMemo, useState } from 'react';
import { RaRecord, RecordRepresentation, useRecordContext, useShowContext } from 'react-admin';

import { Tooltip } from '@mui/material';
import { SimpleTreeView, SimpleTreeViewProps } from '@mui/x-tree-view/SimpleTreeView';

import ToggleOffIcon from '@mui/icons-material/ToggleOff';
import ToggleOnIcon from '@mui/icons-material/ToggleOn';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import SimpleUpdateButton from '../../../jsonapi/components/SimpleUpdateButton';
import { getAnchestors } from '../../MapViewer/utils';
import { getSubTree } from '../../utils';
import useSelectedLayer from './useSelectedLayer';


interface LayerLabelProps {
  record: RaRecord
}

const LayerLabel = ({
  record
}: LayerLabelProps) => {
  
  const { refetch } = useShowContext();

  const toggleIsActive = useMemo(()=>(
    <SimpleUpdateButton
      resource='Layer'
      size='small'
      record={record}
      data={{isActive: !record.isActive}}

      color={record.isActive ? 'success': 'warning'}
      label={'ra.action.toggle'}
      options={{onSuccess: () => refetch()}}
    >
      {record.isActive ? <ToggleOnIcon/>: <ToggleOffIcon/>}
    </SimpleUpdateButton>
  ),[record])

  const toggleIsSearchable = useMemo(()=>(
    <SimpleUpdateButton
      resource='Layer'
      size='small'
      record={record}
      data={{isSearchable: !record.isSearchable}}

      color={record.isSearchable ? 'success': 'warning'}
      label={'ra.action.toggle'}
      options={{onSuccess: () => refetch()}}
    >
      {record.isActive ? <VisibilityIcon/>: <VisibilityOffIcon/>}
    </SimpleUpdateButton>
  ),[record])

  return (
      <div>
          {toggleIsActive}
          {toggleIsSearchable}
          {record.isSpatialSecured ? <Tooltip title="Layer spatial secured"><VpnLockIcon color='info'/></Tooltip>: null}
          <RecordRepresentation record={record}/>
      </div>
  )
};


const WmsTreeView = ({
  ...props
}: SimpleTreeViewProps) => {
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const record = useRecordContext();
  const tree = useMemo(()=> record?.layers && getSubTree(record?.layers.sort((a: RaRecord, b: RaRecord) => a.mpttLft > b.mpttLft), undefined, (r) => ({label: <LayerLabel record={r}/>})) || [],[record?.layers])
  
  const [selectedLayer, setSelectedLayer] = useSelectedLayer(record?.layers[0].id);
  
  const defaultExpandedItems = useMemo<string[]>(()=>{
    if (selectedLayer !== undefined && selectedLayer !== null) {
        const anchestors = getAnchestors(record?.layers.sort((a: RaRecord, b: RaRecord) => a.mpttLft > b.mpttLft), record?.layers.find((layer: RaRecord) => layer.id === selectedLayer))
        return anchestors?.map(layer => layer.id.toString())
    }
    return []
  },[selectedLayer])

  const [expandedItems, setExpandedItems] = useState<string[]>(defaultExpandedItems);

  const onItemExpansionToggle =  useCallback((event: React.SyntheticEvent, itemIds: string[]) => {
  
      if (event.target.closest('.MuiTreeItem-iconContainer')) {
          setExpandedItems(itemIds)

      } else {
          event.stopPropagation();
      }
      
  }, [])


  const onSelectedItemsChange = useCallback( (event: React.SyntheticEvent, itemids: string | null) =>{
    if (event.target.closest('.MuiTreeItem-iconContainer')) {
        return;
    }
    itemids !== null && setSelectedLayer(itemids);
  }, [setSelectedLayer])


  return (
      <SimpleTreeView
                      
        selectedItems={selectedLayer ?? null}

        onSelectedItemsChange={onSelectedItemsChange}
        onExpandedItemsChange={onItemExpansionToggle}

        expandedItems={expandedItems}
        {...props}
      >
      {tree}
    </SimpleTreeView>
  )
}


export default WmsTreeView