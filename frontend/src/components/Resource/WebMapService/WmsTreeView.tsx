import { useCallback, useMemo, useState } from 'react';
import { RaRecord, useRecordContext } from 'react-admin';

import { Tooltip } from '@mui/material';
import { SimpleTreeView, SimpleTreeViewProps } from '@mui/x-tree-view/SimpleTreeView';

import CircleIcon from '@mui/icons-material/Circle';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { getAnchestors } from '../../MapViewer/utils';
import { getSubTree } from '../../utils';



interface LayerLabelProps {
  record: RaRecord
}

const LayerLabel = ({
  record
}: LayerLabelProps) => {
  return (
      <div  >
          {record.isActive ? <Tooltip title="Layer is activated"><CircleIcon color='success'/></Tooltip>: <Tooltip title="Layer is deactivated"><CircleIcon color='warning'/></Tooltip>}
          {record.isSpatialSecured ? <Tooltip title="Layer spatial secured"><VpnLockIcon color='info'/></Tooltip>: null}

          {record.title} 
          
      </div>
  )
};


const WmsTreeView = ({
  ...props
}: SimpleTreeViewProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  const { layerId } = useParams();
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const record = useRecordContext();
  const tree = useMemo(()=> record?.layers && getSubTree(record?.layers.sort((a: RaRecord, b: RaRecord) => a.mpttLft > b.mpttLft), undefined, (r) => ({label: <LayerLabel record={r}/>})) || [],[record?.layers])

  const defaultExpandedItems = useMemo<string[]>(()=>{
    if (layerId !== ':layerId' && layerId) {
        const anchestors = getAnchestors(record?.layers.sort((a: RaRecord, b: RaRecord) => a.mpttLft > b.mpttLft), record?.layers.find((layer: RaRecord) => layer.id === layerId))
        return anchestors.map(layer => layer.id.toString())
    }
    return []
},[layerId])

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

    if (itemids !== null){
        if (layerId === ':layerId'){
            navigate(location.pathname.replace(
                `/:layerId`, 
                `/${itemids}`
            ))
        } else {
            navigate(location.pathname.replace(
                `/${layerId}`, 
                `/${itemids}`
            ))
        }
    }
}, [layerId, navigate, location])


  return (
      <SimpleTreeView
                      
        selectedItems={layerId !== ':layerId' ? layerId: null}

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