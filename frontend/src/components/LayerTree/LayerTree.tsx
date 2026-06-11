import { useCallback, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

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
import { ContextMenuBase, useContextMenuBase } from './ContextMenuBase'
import { DragableTreeItem } from './DragableTreeItem'
import TreeNodeCheckbox from './NodeCheckbox'

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
const { trees, owsContext } = useOwsContextBase()
    const { isOpen, itemId } = useContextMenuBase()

  const defaultExpandedNodes = useMemo(()=> {
    return owsContext.getLeafNodes().map(feature => feature.properties.folder?? '')
  },[owsContext])

  const [expanded, setExpanded] = useState<string[]>([...initialExpanded, ...defaultExpandedNodes])

  const handleToggle = useCallback((event: SyntheticEvent<Element, Event> | null, itemId: TreeViewItemId, isExpanded: boolean): void => {

    const newExpanded = [...expanded, ...defaultExpandedNodes]
    if (isExpanded) {
      if (!newExpanded.includes(itemId)) {
        newExpanded.push(itemId)
      }
    } else {
      const index = newExpanded.indexOf(itemId)
      if (index > -1) {
        newExpanded.splice(index, 1)
      }
    }
    if ((event?.target as HTMLElement).closest('.MuiSvgIcon-root') != null) {
      setExpanded(newExpanded)
    }
  }, [expanded])

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
          <TreeNodeCheckbox node={node} />
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

  return trees?.map(tree => {
      return (
        <SimpleTreeView
          key={tree.id}
          onItemExpansionToggle={handleToggle}
          defaultExpandedItems={defaultExpandedNodes}
          expandedItems={expanded}
          selectedItems={isOpen && itemId ? itemId : null}
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
