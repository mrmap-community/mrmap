import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RaRecord, RecordRepresentation, useRecordContext, useShowContext } from 'react-admin';

import { Tooltip } from '@mui/material';
import { SimpleTreeView, SimpleTreeViewProps } from '@mui/x-tree-view/SimpleTreeView';

import ToggleOffIcon from '@mui/icons-material/ToggleOff';
import ToggleOnIcon from '@mui/icons-material/ToggleOn';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import { TreeItemProps } from '@mui/x-tree-view/TreeItem';
import SimpleUpdateButton from '../../../jsonapi/components/SimpleUpdateButton';
import { getAnchestors } from '../../MapViewer/utils';
import { getSubTree, useQueryParam } from '../../utils';

export interface WmsTreeViewProps extends Omit<SimpleTreeViewProps, 'children'> {
  getLayerProps?: (record: RaRecord) => TreeItemProps;
  record?: RaRecord
  focusSelectedLayer?: boolean
}


interface LayerLabelProps {
  record: RaRecord
}

const LayerLabel = ({
  record
}: LayerLabelProps) => {
  console.log('layer', record)
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
  getLayerProps = (record: RaRecord) => ({itemId: record.id.toString(), label: <LayerLabel record={record}/>}),
  record: wmsRecord,
  focusSelectedLayer = false,
  ...props
}: WmsTreeViewProps) => {

  const containerRef = useRef(null);
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const contextRecord = useRecordContext();
  console.log(contextRecord)
  const record = wmsRecord ?? contextRecord;

  const sortedLayers = useMemo(
    () => [...(record?.layers || [])].sort(
      (a: RaRecord, b: RaRecord) => a.mpttLft - b.mpttLft
    ),
    [record?.layers]
  );
  const tree = useMemo(() => record?.layers && getSubTree(
    sortedLayers, 
    undefined, 
    getLayerProps
  ) || [],
  [record?.layers, getLayerProps])
  
  const [selectedLayer, setSelectedLayer] = useQueryParam('selectedLayer', record?.layers?.[0]?.id.toString());

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

  useEffect(()=>{
    if(focusSelectedLayer && defaultExpandedItems?.length > 0){
      setExpandedItems(defaultExpandedItems);
    }
  },[defaultExpandedItems])


  useEffect(() => {
    if (!focusSelectedLayer || !selectedLayer) return;

    let attempts = 0;

    const tryScroll = () => {
      const el = containerRef.current?.querySelector(
        `[id$="${selectedLayer}"]`
      );

      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else if (attempts < 10) {
        attempts++;
        requestAnimationFrame(tryScroll);
      }
    };

    tryScroll();
  }, [selectedLayer, focusSelectedLayer]);

  return (
    <SimpleTreeView
      ref={containerRef}
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