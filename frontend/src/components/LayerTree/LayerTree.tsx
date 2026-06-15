import { useCallback, useEffect, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

import { SimpleTreeView, TreeViewItemId } from '@mui/x-tree-view'

import AdjustIcon from '@mui/icons-material/AdjustOutlined'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import Dialog from '../Dialog/Dialog'
import { DialogBase } from '../Dialog/DialogContextBase'
import ContextMenu from './ContextMenu'
import { ContextMenuBase } from './ContextMenuBase'
import { DragableTreeItem } from './DragableTreeItem'

export interface LayerTreeProps {
  initialExpanded?: string[]
}

const style = {
  position: 'absolute' as const,
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 400,
  bgcolor: 'background.paper',
  border: '2px solid #000',
  boxShadow: 24,
  p: 4,
};

const darkStyle = {
  ...style,
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
    console.log('onItemSelectionToggle', itemId, feature, isSelected)

    feature && setFeatureActive(itemId, isSelected)
  }, [owsContext])

  const renderTreeItemLabel = useCallback((node: TreeifiedOWSResource) => {
    /* const securityRuleButton = (
      <IconButton>
        {node.record.isSpatialSecured ? <Tooltip title="Spatial secured"><VpnLockIcon /></Tooltip> : node.record.isSecured ? <Tooltip title="Secured"><LockIcon /></Tooltip> : null}
      </IconButton>
    )
 */
    return (
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ width: '100%' }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {/*<TreeNodeCheckbox node={node} />*/}
          {node.properties.title}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {/* icons */}
          <Tooltip title="Root node">
            <AdjustIcon color="primary" fontSize="small" />
          </Tooltip>
        </Box>
      </Stack>
    )
  }, [])

  const renderTree = useCallback((node?: TreeifiedOWSResource): ReactNode => {
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
      ) : <></>
  },[renderTreeItemLabel])

  useEffect(()=>{
    console.log('selectedItems changed', selectedItems)
    console.log('active', owsContext.features.filter(f=>f.properties.active === true))
  },[selectedItems])

  
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
