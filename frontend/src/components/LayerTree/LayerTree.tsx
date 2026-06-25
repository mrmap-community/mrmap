import { useCallback, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

import { SimpleTreeView, TreeViewItemId } from '@mui/x-tree-view'

import VpnLockIcon from '@mui/icons-material/VpnLock'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import { Loading, useGetOne } from 'react-admin'
import { OWSResource } from '../../ows-lib/OwsContext/core'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import Dialog from '../Dialog/Dialog'
import { DialogBase } from '../Dialog/DialogContextBase'
import ContextMenu from './ContextMenu'
import { ContextMenuBase } from './ContextMenuBase'
import { DragableTreeItem } from './DragableTreeItem'

export interface LayerTreeProps {
  initialExpanded?: string[]
}

export interface NodeIconsProps {
  node: OWSResource
}

const NodeIcons = ({node}: NodeIconsProps) => {
  const layerId = useMemo(() =>
    typeof node.getWmsGetMapOperation === 'function'
      ? node.getWmsGetMapOperation()?.['x-mrmap-layer-id']
      : undefined
  , [node])
  const {data: layer, isLoading} = useGetOne("Layer", {id: layerId}, {enabled: !!layerId})


  if (isLoading){
    return <Loading />
  }

  return (
    <div>
      {
        layer?.isSpatialSecured ? 
          <Tooltip title="Layer is spatial secured">
            <VpnLockIcon color="warning" fontSize="small" />
          </Tooltip>: 
        null
      }
    </div>
  )
}


const TreeViews = (
  { initialExpanded = [] }: LayerTreeProps
) => {
const { trees, owsContext, setFeatureActive } = useOwsContextBase()

  const defaultExpandedNodes = useMemo(()=> owsContext.getLeafNodes().map(feature => feature.properties.folder ?? ''),[owsContext])
  const selectedItems = useMemo(() => owsContext.getActiveFeatures().map(feature => feature.properties.folder ?? ''),[owsContext])

  const [expanded, setExpanded] = useState<string[] >([...initialExpanded, ...defaultExpandedNodes])

  const onItemExpansionToggle = useCallback(
  (
    event: SyntheticEvent<Element, Event> | null,
    itemId: TreeViewItemId,
    isExpanded: boolean,
  ) => {
    if (!(event?.target as HTMLElement)?.closest(".MuiSvgIcon-root")) {
      return;
    }
    setExpanded(prev =>
      isExpanded
        ? [...new Set([...prev, itemId])]
        : prev.filter(id => id !== itemId)
    );
  },
  [],
);

  const onItemSelectionToggle = useCallback((
    event: React.SyntheticEvent | null, 
    itemId: TreeViewItemId, 
    isSelected: boolean
  )=>{
    event?.preventDefault()
    event?.stopPropagation()
    const feature = owsContext.findResourceByFolder(itemId)
    feature && setFeatureActive(itemId, isSelected)
  }, [owsContext])

  

  const renderTreeItemLabel = useCallback((node: OWSResource) => {
    /* const securityRuleButton = (
      <IconButton>
        {node.record.isSpatialSecured ? <Tooltip title="Spatial secured"><VpnLockIcon /></Tooltip> : node.record.isSecured ? <Tooltip title="Secured"><LockIcon /></Tooltip> : null}
      </IconButton>
    )
 */
    return (
      <Stack
        direction={"row"}
        justifyContent={"space-between"}
      >
        <Box>
          {node.properties.title}
        </Box>
        <Box>
          {/* icons */}
          <NodeIcons node={node}/>
        </Box>
      </Stack>
    )
  }, [])

  const renderTree = useCallback((node?: OWSResource): ReactNode => {
    return node !== undefined ? (
        <DragableTreeItem
          node={node}                    
          key={node.properties.folder}
          itemId={node.properties.folder}
          label={renderTreeItemLabel(node)}
        >
          {
            Array.isArray(node.children)
              ? node.children.map((node) => { return renderTree(node) })
              : null
          }
        </DragableTreeItem >
      ) : <div></div>
  },[renderTreeItemLabel])
  
  return trees?.map(tree => {
      return (
        <SimpleTreeView
          key={tree.id}
          onItemExpansionToggle={onItemExpansionToggle}
          defaultExpandedItems={defaultExpandedNodes}
          expandedItems={expanded}
                    
          checkboxSelection={true}
          multiSelect={true}

          onItemSelectionToggle={onItemSelectionToggle}
          selectedItems={selectedItems}
        >
          {renderTree(tree)}
        </SimpleTreeView>
      )
    })
 
}

const LayerTree = ({ 
  initialExpanded = [] 
}: LayerTreeProps): ReactNode => {
  return (
    <DialogBase>
      <ContextMenuBase>
        <TreeViews initialExpanded={initialExpanded} />
        <ContextMenu />
        <Dialog/>
      </ContextMenuBase>
    </DialogBase>
  )
}

export default LayerTree
