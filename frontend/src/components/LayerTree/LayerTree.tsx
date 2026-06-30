import { memo, useCallback, useEffect, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

import { SimpleTreeView, TreeViewItemId } from '@mui/x-tree-view'

import PowerIcon from '@mui/icons-material/Power'
import PowerOffIcon from '@mui/icons-material/PowerOff'
import VpnLockIcon from '@mui/icons-material/VpnLock'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import { useGetMany } from 'react-admin'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import Dialog from '../Dialog/Dialog'
import { DialogBase } from '../Dialog/DialogContextBase'
import ContextMenu from './ContextMenu'
import { ContextMenuBase } from './ContextMenuBase'
import { DragableTreeItem } from './DragableTreeItem'

export interface LayerTreeProps {
  initialExpanded?: string[]
}

export interface LayerProperties {
  isActive?: boolean;
  isSpatialSecured?: boolean;
}

const NodeIcons = memo(
  ({ isActive, isSpatialSecured }: LayerProperties) => (
    <div>
      {isActive ? (
        <Tooltip title="Layer is active">
          <PowerIcon color="success" fontSize="small" />
        </Tooltip>
      ) : (
        <Tooltip title="Layer is not active">
          <PowerOffIcon color="error" fontSize="small" />
        </Tooltip>
      )}

      {isSpatialSecured && (
        <Tooltip title="Layer is spatial secured">
          <VpnLockIcon color="warning" fontSize="small" />
        </Tooltip>
      )}
    </div>
  )
);


export interface TreeItemLabelProps {
  title: string;
  isActive?: boolean;
  isSpatialSecured?: boolean;
}

const TreeItemLabel = memo(
  ({ title, isActive, isSpatialSecured }: TreeItemLabelProps) => (
    <Stack direction="row" justifyContent="space-between">
      <Box>{title}</Box>

      <Box>
        <NodeIcons
          isActive={isActive}
          isSpatialSecured={isSpatialSecured}
        />
      </Box>
    </Stack>
  )
);

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

  const renderTree = useCallback((node?: OWSResource): ReactNode => {
    const layerProperties = node?.getWmsGetMapOperation?.()?.["x-mrmap-layer-properties"] as LayerProperties | undefined;
    return node !== undefined ? (
        <DragableTreeItem
          node={node}                    
          key={node.properties.folder}
          itemId={node.properties.folder}
          label={
            <TreeItemLabel
          title={node.properties.title}
          isActive={layerProperties?.isActive}
          isSpatialSecured={layerProperties?.isSpatialSecured}
      />

          }
        >
          {
            Array.isArray(node.children)
              ? node.children.map((node) => { return renderTree(node) })
              : null
          }
        </DragableTreeItem >
      ) : <div></div>
  },[])

  return trees?.map(tree => {
      return (
        <SimpleTreeView
          key={tree.id}
          onItemExpansionToggle={onItemExpansionToggle}
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
  const { owsContext, setOwsContext } = useOwsContextBase()
  
  const mrmapLayers = useMemo(()=>(
    [
      ...new Set(
        owsContext.features
          .map(
            feature =>
              feature.getWmsGetMapOperation()?.["x-mrmap-layer-id"]
          )
          .filter(Boolean)
      )
    ]
  ),[owsContext])

  const {
    data,
  } = useGetMany(
    "Layer", 
    {
      ids: mrmapLayers,
      meta: {
        jsonApiParams:{
          'fields[Layer]': 'identifier,is_spatial_secured,is_active'
        }
      }
    },
    {
      enabled: mrmapLayers.length > 0
    }
  )
  useEffect(()=>{
      const newContext = OWSContext.fromPlainObject(owsContext)
      const offerings = newContext.features.flatMap(
        feature => feature.properties.offerings ?? []
      ).flatMap(
        offering => offering.operations ?? []
      )
      
      data?.forEach(layer => {
        const offering = offerings.find(offering => offering["x-mrmap-layer-id"] === layer.id)
        if (offering !== undefined) {
          offering["x-mrmap-layer-properties"] = {...layer}
        }
      })

      setOwsContext(newContext)
    
  },[data])
  
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
