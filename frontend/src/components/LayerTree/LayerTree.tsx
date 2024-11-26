import { useCallback, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

import { SimpleTreeView } from '@mui/x-tree-view'

import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
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

const LayerTree = ({ 
  initialExpanded = [] 
}: LayerTreeProps): ReactNode => {
  const { trees, owsContext } = useOwsContextBase()

  const defaultExpandedNodes = useMemo(()=> {
    return owsContext.getLeafNodes().map(feature => feature.properties.folder?? '')
  },[owsContext])

  const [expanded, setExpanded] = useState<string[]>([...initialExpanded, ...defaultExpandedNodes])

  const handleToggle = useCallback((event: SyntheticEvent, nodeId: string, isExpanded: boolean): void => {

    const newExpanded = [...expanded, ...defaultExpandedNodes]
    if (isExpanded) {
      if (!newExpanded.includes(nodeId)) {
        newExpanded.push(nodeId)
      }
    } else {
      const index = newExpanded.indexOf(nodeId)
      if (index > -1) {
        newExpanded.splice(index, 1)
      }
    }
    if ((event.target as HTMLElement).closest('.MuiSvgIcon-root') != null) {
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
      <>
        <TreeNodeCheckbox node={node} />
        {/* {securityRuleButton} */}
        {node.properties.title}
        {/* <ContextMenu node={node} map={map}/> */}
      </>
    )
  }, [])

  const renderTree = useCallback((node?: TreeifiedOWSResource): ReactNode => {
    if (node !== undefined) {
      return (<DragableTreeItem
                node={node}                    
                key={node.properties.folder}
                label={renderTreeItemLabel(node)}
              >
                {
                  Array.isArray(node.children)
                    ? node.children.map((node) => { return renderTree(node) })
                    : null
                }
              </DragableTreeItem >)


    }
    return <></>
  }, [renderTreeItemLabel])

  const treeViews = useMemo(() => {
    return trees?.map(tree => {
      return (
        <SimpleTreeView
          key={tree.id}
          onItemExpansionToggle={handleToggle}
          defaultExpandedItems={defaultExpandedNodes}
          expandedItems={expanded}
        >
          {renderTree(tree)}
        </SimpleTreeView>
      )
    })
  }, [trees, handleToggle, expanded, renderTree])

  return (
    <>
      {treeViews}
    </>
  )
}

export default LayerTree
