import { memo, useCallback, useMemo, useState, type ReactNode, type SyntheticEvent } from 'react'

import { SimpleTreeView, TreeViewItemId } from '@mui/x-tree-view'

import PowerIcon from '@mui/icons-material/Power'
import PowerOffIcon from '@mui/icons-material/PowerOff'
import VpnLockIcon from '@mui/icons-material/VpnLock'
import Box from '@mui/material/Box'
import Checkbox from '@mui/material/Checkbox'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { Identifier, ListContextProvider, ListControllerResult, RaRecord, RecordContextProvider, useGetMany, useRecordContext } from 'react-admin'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import Dialog from '../Dialog/Dialog'
import { DialogBase } from '../Dialog/DialogContextBase'
import ContextMenu from './ContextMenu/ContextMenu'
import { ContextMenuBase } from './ContextMenu/ContextMenuBase'
import { DragableTreeItem } from './DragableTreeItem'

import { v4 as uuidv4 } from 'uuid'
import { useMapViewerBase } from '../MapViewer/MapViewerBase'



export interface LayerTreeProps {
  initialExpanded?: string[],
  layers?: RaRecord[]
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
  node: OWSResource;
}

const TreeItemLabel = memo(
  ({
    node
  }: TreeItemLabelProps) => {
    const record = useRecordContext()
    const { owsContext, setOwsContext } = useOwsContextBase()
    const { mapLoading } = useMapViewerBase()

    const hasError = useMemo(()=>{
      const hasError = mapLoading.failedFeatures.some(feature => feature.properties.folder === node.properties.folder)
      if (hasError) {
        return mapLoading.errors.find(error => error.features?.some(feature => feature.properties.folder === node.properties.folder))?.message || ''
      }
    }, [mapLoading.errors, node.properties.folder])

    const indeterminateVisibility = useMemo(() => {
      const mapOperations = owsContext
        .getDescandantsOf(node, true)
        .map(descendant => descendant.getWmsOperationByCode('GetMap'))
        .filter((operation) => operation !== undefined)

      if (mapOperations.length === 0) {
        return false
      }

      const hasActive = mapOperations.some(operation => operation.active === true)
      const hasInactive = mapOperations.some(operation => operation.active !== true)

      return hasActive && hasInactive
    }, [owsContext, node])

    const indeterminateQueryability = useMemo(() => {
      const mapOperations = owsContext
        .getDescandantsOf(node, true)
        .map(descendant => descendant.getWmsOperationByCode('GetFeatureInfo'))
        .filter((operation) => operation !== undefined)

      if (mapOperations.length === 0) {
        return false
      }

      const hasActive = mapOperations.some(operation => operation.active === true)
      const hasInactive = mapOperations.some(operation => operation.active !== true)

      return hasActive && hasInactive
    }, [owsContext, node])

    const toggle = useCallback(
      (operationCode: 'GetMap' | 'GetFeatureInfo') =>
        (event: React.ChangeEvent<HTMLInputElement, Element>, checked: boolean) => {
          event.preventDefault()
          event.stopPropagation()
          

          const newContext = OWSContext.fromPlainObject(owsContext)
          const target = newContext.findResourceByFolder(node.properties.folder)
          if (target === undefined) return

          const updateOperationState = (resource: OWSResource | undefined) => {
            const operation = resource?.getWmsOperationByCode(operationCode)
            if (operation) {
              operation['active'] = checked
            }
          }

          updateOperationState(target)

          // activate/deactivate all descendants
          newContext.getDescandantsOf(target, true).forEach(descendant => {
            updateOperationState(descendant)
          })

          // set parent also active if all siblings of target are active
          if (checked === true && newContext.getSiblingsOf(target).every(feature => feature.getWmsOperationByCode(operationCode)?.active === true)) {
            const parent = newContext.getParentOf(target)
            updateOperationState(parent)
          }
          // deactivate parent to prevent from parent layer using for getmap calls etc.
          else if (checked === false) {
            newContext.getAncestorsOf(target).forEach(ancestor => {
              updateOperationState(ancestor)
            })
          }

          setOwsContext(newContext)
        },
      [node.properties.folder, owsContext, setOwsContext],
    )


    return (
      <Stack direction="row" sx={{ justifyContent: "flex-start", }}>
        <Box sx={{display:"flex", alignItems:"flex-start"}} >
         <Tooltip title="Toggle the visibility of this service">
          <Checkbox
            size="small"
            disableRipple
            sx={{
              p: 0.25,
              mr: 0.25,
              
            }}
            onClick={(event)  => event.stopPropagation()}
            checked={node?.getWmsOperationByCode("GetMap")?.active as boolean ?? false}
            indeterminate={indeterminateVisibility}
            onChange={toggle('GetMap')}
          />
        </Tooltip>
        <Tooltip title="Toggle the queryability of this service">
          <Checkbox
            size="small"
            disableRipple
            sx={{
              p: 0.25,
              mr: 0.25,
            }}
            onClick={(event)  => event.stopPropagation()}
            checked={node?.getWmsOperationByCode("GetFeatureInfo")?.active as boolean ?? false}
            indeterminate={indeterminateQueryability}
            onChange={toggle('GetFeatureInfo')}
            disabled={node.getWmsOffering()?.operations?.find(op => op.code === 'GetFeatureInfo') === undefined}
          />
        </Tooltip>
        <Box sx={{display:"flex", alignItems:"center"}} >
          {hasError !== undefined ? 
             <Tooltip
                title={`Requesting Layer failed: ${hasError}`}
              >
            <Typography variant="body2" color='warning'>{node.properties.title}</Typography>
          </Tooltip>:
          <Typography variant="body2">{node.properties.title}</Typography>
        }
         
        </Box>
      </Box>

      <Stack direction="row" sx={{ justifyContent: "flex-end", alignItems:"center", ml: "auto"}}>
        <NodeIcons
          isActive={record?.isActive}
          isSpatialSecured={record?.isSpatialSecured}
        />
      </Stack>
    </Stack>
    )
  }
);

const TreeViews = (
  { 
    initialExpanded = [],
    layers
  }: LayerTreeProps
) => {
  const { trees, owsContext, setFeatureActive } = useOwsContextBase()
  const defaultExpandedNodes = useMemo(()=> owsContext.getLeafNodes().map(feature => feature.properties.folder ?? ''),[owsContext])
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
    const itemId = node?.properties.folder ?? uuidv4();
    // In OWSContext a node has properties.offerings.
    // Offerings have operations like GetMap, GetFeatureInfo, etc.
    // We differentiate between offerings like GetMap which are raster based and GetFeatureInfo which responses with vector data.
    // Any folder in our suitecase can have one offering with a raster based operation and one vector based operation.
    
    // So the tree shall shall look like this:
    // node (folder)
    //   - offering (title)
    //     - operation (GetMap, GetFeatureInfo, etc.)
    //     - styles
    const layerId = node?.getWmsOperationByCode("GetMap")?.["x-mrmap-layer-id"] as Identifier
    const layerRecord = layerId ? layers?.find(layer => layer.id === layerId) : undefined

    return node !== undefined ? (
        <RecordContextProvider
          value={layerRecord}
        >
          <DragableTreeItem
            node={node}                    
            key={node.properties.folder}
            itemId={itemId}
            label={
              <TreeItemLabel
                node={node}
              />
            }
          >
            {
              Array.isArray(node.children)
                ? node.children.map((node) => { return renderTree(node) })
                : null
            }
          </DragableTreeItem >
        </RecordContextProvider>
      ) : <div></div>
  },[layers])

  return trees?.map(tree => {
      return (
        <SimpleTreeView
          key={tree.id}
          onItemExpansionToggle={onItemExpansionToggle}
          onItemSelectionToggle={onItemSelectionToggle}
          expandedItems={expanded}
          //selectedItems={selectedItems.length > 0 ? selectedItems : null}
          disableSelection
        >
          {renderTree(tree)}
        </SimpleTreeView>
      )
    })
 
}

const LayerTree = ({ 
  initialExpanded = [] 
}: LayerTreeProps): ReactNode => {
  const { owsContext } = useOwsContextBase()
  
  const mrmapLayers = useMemo(()=>(
    [
      ...new Set(
        owsContext.features
          .map(
            feature =>
              feature.getWmsOperationByCode("GetMap")?.["x-mrmap-layer-id"]
          )
          .filter(Boolean)
      )
    ]
  ),[owsContext])

  const {
    data,
    refetch
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

  const listContext = useMemo(() => {
    const ids = Array.isArray(data) ? data.map(d => d.id as Identifier) : []
    const dataObject: Record<string, RaRecord> = {}
    data?.forEach((d: RaRecord) => {
      if (d && d.id !== undefined) dataObject[d.id as Identifier] = d
    })

    return {
      ids,
      data: dataObject,
      total: ids.length,
      page: 1,
      perPage: ids.length || 0,
      loaded: !!data,
      refetch,
    }
  }, [data, refetch]) as unknown as ListControllerResult

  return (
    <DialogBase>
      <ListContextProvider value={listContext}>
        <ContextMenuBase>
          <TreeViews initialExpanded={initialExpanded} layers={data} />
          <ContextMenu />
          <Dialog/>
        </ContextMenuBase>
      </ListContextProvider>
    </DialogBase>
  )
}

export default LayerTree
