import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RaRecord, RecordRepresentation, useRecordContext, useShowContext } from 'react-admin';

import { Tooltip } from '@mui/material';
import { useSimpleTreeViewApiRef } from '@mui/x-tree-view/hooks';
import { SimpleTreeView, SimpleTreeViewProps } from '@mui/x-tree-view/SimpleTreeView';

import ToggleOffIcon from '@mui/icons-material/ToggleOff';
import ToggleOnIcon from '@mui/icons-material/ToggleOn';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import VpnLockIcon from '@mui/icons-material/VpnLock';
import { TreeItemProps } from '@mui/x-tree-view/TreeItem';
import SimpleUpdateButton from '../../../../jsonapi/components/SimpleUpdateButton';
import { getAnchestors } from '../../../MapViewer/utils';
import { getSubTree, useQueryParam } from '../../../utils';

export interface WmsTreeViewProps extends Omit<SimpleTreeViewProps<false>, 'children'> {
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
  const { refetch } = useShowContext();

  const hasIsActive = Object.prototype.hasOwnProperty.call(record, 'isActive');
  const hasIsSearchable = Object.prototype.hasOwnProperty.call(record, 'isSearchable');


  const toggleIsActive = useMemo(()=>(
    <SimpleUpdateButton
      resource='Layer'
      size='small'
      record={record}
      data={{isActive: !record.isActive}}
      disabled={!hasIsActive}
      color={hasIsActive && record.isActive ? 'success' : 'warning'}
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
      disabled={!hasIsSearchable}
      color={hasIsSearchable && record.isSearchable ? 'success' : 'warning'}
      label={'ra.action.toggle'}
      options={{onSuccess: () => refetch()}}
    >
      {record.isActive ? <VisibilityIcon/>: <VisibilityOffIcon/>}
    </SimpleUpdateButton>
  ),[record])

  return (
      <Fragment>
          {toggleIsActive}
          {toggleIsSearchable}
          {record.isSpatialSecured ? <Tooltip title="Layer spatial secured"><VpnLockIcon color='info'/></Tooltip>: null}
          <RecordRepresentation record={record}/>
      </Fragment>
  )
};


const WmsTreeView = ({
  getLayerProps = (record: RaRecord) => ({itemId: record.id.toString(), label: <LayerLabel record={record}/>}),
  record: wmsRecord,
  focusSelectedLayer = false,
  ...props
}: WmsTreeViewProps) => {

  const containerRef = useRef<HTMLUListElement>(null);
  const apiRef = useSimpleTreeViewApiRef();
  // this is the wms service record with all includes layers which are fetched in the parent component.
  const contextRecord = useRecordContext();
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

  const effectiveSelectedLayer = props.selectedItems !== undefined
    ? props.selectedItems
    : selectedLayer;
  const defaultExpandedItems = useMemo<string[]>(() => {
    const layer = sortedLayers.find((item) => String(item.id) === effectiveSelectedLayer);
    return layer ? getAnchestors(sortedLayers, layer).map((item) => String(item.id)) : [];
  }, [sortedLayers, effectiveSelectedLayer]);

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
  },[defaultExpandedItems, focusSelectedLayer])


  useEffect(() => {
    if (!focusSelectedLayer || !effectiveSelectedLayer) return;

    let attempts = 0;
    let frame: number;
    const tryScroll = () => {
      const container = containerRef.current;
      if (!container) return;
      const el = apiRef.current?.getItemDOMElement(effectiveSelectedLayer);
      const content = el?.querySelector('.MuiTreeItem-content') ?? el;
      const itemBounds = content?.getBoundingClientRect();
      if (!itemBounds || itemBounds.height === 0) {
        if (attempts++ < 30) frame = requestAnimationFrame(tryScroll);
        return;
      }
      const containerBounds = container.getBoundingClientRect();
      if (itemBounds.top < containerBounds.top || itemBounds.bottom > containerBounds.bottom) {
        container.scrollTo({
          top: container.scrollTop + itemBounds.top - containerBounds.top
            - (container.clientHeight - itemBounds.height) / 2,
          behavior: 'smooth',
        });
      }
    };

    const container = containerRef.current;
    container?.addEventListener('transitionend', tryScroll);
    frame = requestAnimationFrame(tryScroll);
    return () => {
      cancelAnimationFrame(frame);
      container?.removeEventListener('transitionend', tryScroll);
    };
  }, [effectiveSelectedLayer, focusSelectedLayer, tree, props.expandedItems, expandedItems]);

  return (
    <SimpleTreeView
      ref={containerRef}
      apiRef={apiRef}
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