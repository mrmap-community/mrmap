import { Fragment, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode, type SyntheticEvent } from 'react'
import { Identifier, ListContextProvider, ListControllerResult, RaRecord, RecordContextProvider, useGetMany, useRecordContext, useTranslate } from 'react-admin'
import { createPortal } from 'react-dom'

import MoreVertIcon from '@mui/icons-material/MoreVert'
import PaletteOutlinedIcon from '@mui/icons-material/PaletteOutlined'
import PowerIcon from '@mui/icons-material/Power'
import PowerOffIcon from '@mui/icons-material/PowerOff'
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import VpnLockIcon from '@mui/icons-material/VpnLock'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import { Button, ButtonBase, Paper } from '@mui/material'
import Box from '@mui/material/Box'
import Checkbox from '@mui/material/Checkbox'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { SimpleTreeView, TreeViewItemId } from '@mui/x-tree-view'
import { DomEvent } from 'leaflet'
import { v4 as uuidv4 } from 'uuid'

import { getUnsupportedReasons, unsupportedReasonLabel } from '../../ows-lib/OwsContext/capabilities'
import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { getWmsDimensionOverrides } from '../../ows-lib/OwsContext/dimensions'
import { isWithinScaleLimits } from '../../ows-lib/OwsContext/scales'
import { getWmsOperationStyles } from '../../ows-lib/OwsContext/utils'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'
import Dialog from '../Dialog/Dialog'
import { DialogBase } from '../Dialog/DialogContextBase'
import { useMapViewerBase } from '../MapViewer/MapViewerBase'
import ContextMenu from './ContextMenu/ContextMenu'
import { ContextMenuBase, context as LayerControlsContext, useContextMenuBase } from './ContextMenu/ContextMenuBase'
import { WmsDimensionControls } from './ContextMenu/DimensionItem'
import { StyleLegendPreview, WmsStyleControls } from './ContextMenu/StyleLegendItem'
import { DragableTreeItem } from './DragableTreeItem'



export interface LayerTreeProps {
  initialExpanded?: string[],
  layers?: RaRecord[]
  featureTypes?: RaRecord[]
}

export interface LayerProperties {
  isActive?: boolean;
  isSpatialSecured?: boolean;
}

const NodeIcons = memo(
  ({ isActive, isSpatialSecured }: LayerProperties) => (
    <Fragment>
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
    </Fragment>
  )
);


export interface TreeItemLabelProps {
  node: OWSResource;
}

NodeIcons.displayName = "NodeIcons";

// Raster activation belongs to GetMap; vector activation belongs to WMS identify and WFS resources.
const getLayerStates = (resource: OWSResource, operationCode: 'GetMap' | 'GetFeatureInfo') => {
  const operation = resource.getWmsOperationByCode(operationCode)
  return [
    ...(operation === undefined ? [] : [operation]),
    ...(operationCode === 'GetFeatureInfo' && resource.getWfsOffering() !== undefined
      ? [resource.properties]
      : []),
  ]
}

const TreeItemLabel = memo(
  ({
    node
  }: TreeItemLabelProps) => {
    const record = useRecordContext()
    const translate = useTranslate()
    const { setContextMenu, controlsId, setControlsId } = useContextMenuBase()
    const { owsContext, setOwsContext } = useOwsContextBase()
    const { mapLoading, scaleDenominator } = useMapViewerBase()

    const offering = node.getWmsOffering()
    const hasControls = Boolean(offering?.styles?.some(style => style.name.trim()) || offering?.dimensions?.length)
    const expandedControls = controlsId === node.id

    // an out of scale layer keeps its activation and is only not rendered, so the tree says so
    const isOutOfScale = useMemo(() =>
      node.getWmsOperationByCode('GetMap')?.active === true &&
      !isWithinScaleLimits(node.properties, scaleDenominator),
    [node, scaleDenominator])

    const hasError = useMemo(()=>{
      const hasError = mapLoading.failedFeatures.some(feature => feature.properties.folder === node.properties.folder)
      if (hasError) {
        return mapLoading.errors.find(error => error.features?.some(feature => feature.properties.folder === node.properties.folder))?.message || ''
      }
    }, [mapLoading.errors, node.properties.folder])

    // what the viewer cannot use about this resource; a group answers through its children and
    // carries no offerings of its own, so only childless nodes are asked
    const unsupportedReasons = useMemo(() =>
      node.children.length === 0 ? getUnsupportedReasons(node) : [],
    [node])

    const layerStates = useMemo(() => {
      const subtree = owsContext.getDescandantsOf(node, true)
      return {
        raster: subtree.flatMap(resource => getLayerStates(resource, 'GetMap')),
        vector: subtree.flatMap(resource => getLayerStates(resource, 'GetFeatureInfo')),
      }
    }, [owsContext, node])

    const isChecked = (operationCode: 'GetMap' | 'GetFeatureInfo') => {
      const ownStates = getLayerStates(node, operationCode)
      const states = ownStates.length > 0 ? ownStates
        : operationCode === 'GetMap' ? layerStates.raster : layerStates.vector
      return states.length > 0 && states.every(state => state.active === true)
    }

    const isIndeterminate = (states: ReturnType<typeof getLayerStates>) =>
      states.some(state => state.active === true) && states.some(state => state.active !== true)

    const toggle = useCallback(
      (operationCode: 'GetMap' | 'GetFeatureInfo') =>
        (event: React.ChangeEvent<HTMLInputElement, Element>, checked: boolean) => {
          event.stopPropagation()
          const newContext = OWSContext.fromPlainObject(owsContext)
          const target = newContext.findResourceByFolder(node.properties.folder)
          if (target === undefined) return

          const updateState = (resource: OWSResource) => {
            getLayerStates(resource, operationCode).forEach(state => { state.active = checked })
          }
          newContext.getDescandantsOf(target, true).forEach(updateState)

          // Update ancestors only within this channel, leaving raster and vector independent.
          newContext.getAncestorsOf(target).reverse().forEach(ancestor => {
            const descendantStates = newContext.getDescandantsOf(ancestor)
              .flatMap(resource => getLayerStates(resource, operationCode))
            if (!checked || descendantStates.every(state => state.active === true)) {
              updateState(ancestor)
            }
          })
          setOwsContext(newContext)
        },
      [node.properties.folder, owsContext, setOwsContext],
    )

    return (
      <Stack direction="row" sx={{ alignItems: 'center', minWidth: 0, width: '100%' }}>
        <Box sx={{display:"flex", alignItems:"center", minWidth: 0}} >
         <Tooltip title={translate('LayerTree.raster')}>
          <Checkbox
            size="small"
            disableRipple
            sx={{
              p: 0.25,
              mr: 0.25,
              
            }}
            onClick={(event)  => event.stopPropagation()}
            checked={isChecked('GetMap')}
            indeterminate={isIndeterminate(layerStates.raster)}
            onChange={toggle('GetMap')}
            disabled={layerStates.raster.length === 0}
            slotProps={{ input: { 'aria-label': translate('LayerTree.raster') } }}
          />
        </Tooltip>
        <Tooltip title={translate('LayerTree.vector')}>
          <Checkbox
            size="small"
            disableRipple
            sx={{
              p: 0.25,
              mr: 0.25,
            }}
            onClick={(event)  => event.stopPropagation()}
            checked={isChecked('GetFeatureInfo')}
            indeterminate={isIndeterminate(layerStates.vector)}
            onChange={toggle('GetFeatureInfo')}
            disabled={layerStates.vector.length === 0}
            slotProps={{ input: { 'aria-label': translate('LayerTree.vector') } }}
          />
        </Tooltip>
        <ButtonBase disabled={!hasControls} aria-pressed={hasControls ? expandedControls : undefined}
          aria-label={hasControls ? translate('viewerControls.edit', { layer: node.properties.title }) : undefined}
          onMouseDown={event => event.stopPropagation()}
          onClick={event => { event.stopPropagation(); setControlsId(node.id) }}
          sx={{ minWidth: 0, justifyContent: 'flex-start', textAlign: 'left', py: 0.75, color: expandedControls ? 'primary.main' : 'inherit' }}>
          <Typography variant="body2" noWrap color={hasError !== undefined ? 'warning.main' : undefined}>{node.properties.title}</Typography>
        </ButtonBase>
      </Box>

      <Stack direction="row" sx={{ justifyContent: "flex-end", alignItems:"center", ml: "auto", flexShrink: 0}}>
        {isOutOfScale &&
          <Tooltip title={translate('viewerScale.notRendered', {
            min: node.properties.minscaledenominator ?? 0,
            max: node.properties.maxscaledenominator ?? '∞',
            current: scaleDenominator === undefined ? '-' : Math.round(scaleDenominator),
          })}>
            <Box component="span" aria-label={translate('viewerScale.notRenderedShort')} sx={{ display: 'flex' }}>
              <VisibilityOffIcon color="warning" fontSize="small" />
            </Box>
          </Tooltip>}
        {getWmsOperationStyles(node.getWmsOperationByCode('GetMap')).some(item => item.style !== '') &&
          <Tooltip title={<StyleLegendPreview folder={node.properties.folder} />} describeChild>
            <Box component="span" tabIndex={0} aria-label={translate('viewerStyles.custom')} sx={{ display: 'flex' }}>
              <PaletteOutlinedIcon color="info" fontSize="small" />
            </Box>
          </Tooltip>}
        {getWmsDimensionOverrides(node.getWmsOffering()).length > 0 &&
          <Tooltip title={<Stack><Typography variant="caption">{translate('viewerDimensions.custom')}</Typography>{getWmsDimensionOverrides(node.getWmsOffering()).map(item => <Typography key={item.name} variant="caption" sx={{ overflowWrap: 'anywhere' }}>{item.name}: {item.value}</Typography>)}</Stack>}>
            <Box component="span" tabIndex={0} aria-label={translate('viewerDimensions.custom')} sx={{ display: 'flex' }}><TuneOutlinedIcon color="info" fontSize="small" /></Box>
          </Tooltip>}
        {unsupportedReasons.length > 0 &&
          <Tooltip
            title={
              <Stack spacing={0.5}>
                <Typography variant="caption">{translate('viewerUnsupported.resource')}</Typography>
                {unsupportedReasons.map((reason, index) => (
                  <Typography variant="caption" key={index}>
                    {unsupportedReasonLabel(reason, translate)}
                  </Typography>
                ))}
              </Stack>
            }
            describeChild
          >
            <Box component="span" aria-label={translate('viewerUnsupported.resource')} sx={{ display: 'flex' }}>
              <WarningAmberIcon color="warning" fontSize="small" />
            </Box>
          </Tooltip>}
        <NodeIcons
          isActive={record?.isActive}
          isSpatialSecured={record?.isSpatialSecured}
        />
        <IconButton
          size="small"
          aria-label={translate('viewerStyles.options', { layer: node.properties.title })}
          onMouseDown={event => event.stopPropagation()}
          onClick={event => {
            event.stopPropagation()
            const anchor = event.currentTarget
            const bounds = anchor.getBoundingClientRect()
            setContextMenu({
              node, record, itemId: node.properties.folder,
              isOpen: true, anchorElement: anchor,
              mouseX: bounds.right, mouseY: bounds.bottom,
            })
          }}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Stack>
    )
  }
);

/** Shared controls live outside the tree so editing never changes its row heights. */
export const LayerControlsPanel = () => {
  const { controlsId, setControlsId, pinnedId, setPinnedId } = useContextMenuBase();
  const { owsContext } = useOwsContextBase();
  const translate = useTranslate();
  const node = controlsId === undefined ? undefined : owsContext.features.find(feature => feature.id === controlsId);
  const offering = node?.getWmsOffering();
  const hasStyles = offering?.styles?.some(style => style.name.trim());
  const hasDimensions = Boolean(offering?.dimensions?.length);
  const hasTime = offering?.dimensions?.some(dimension => /^(?:dim_)?time$/i.test(dimension.name) || dimension.units === 'ISO8601');
  useEffect(() => { if (controlsId !== undefined && !node) setControlsId(undefined); }, [controlsId, node, setControlsId]);
  if (!node) return <Typography variant="body2" color="text.secondary">{translate('viewerControls.selectLayer')}</Typography>;
  const title = [...owsContext.getAncestorsOf(node), node].map(feature => feature.properties.title).join(' / ');
  return <Stack role="region" aria-label={translate('viewerControls.edit', { layer: node.properties.title })} spacing={1} sx={{ minWidth: 0 }}>
    <Stack direction="row" sx={{ alignItems: 'center', gap: 1 }}>
      <Typography variant="subtitle2" sx={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>{title}</Typography>
      {hasTime && <Button size="small" onClick={() => setPinnedId(pinnedId === node.id ? undefined : node.id)}>{translate(pinnedId === node.id ? 'viewerControls.unpin' : 'viewerControls.pin')}</Button>}
      <Button size="small" onClick={() => setControlsId(undefined)}>{translate('ra.action.close')}</Button>
    </Stack>
    <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: hasStyles && hasDimensions ? 'minmax(220px, .6fr) minmax(0, 1.4fr)' : 'minmax(0, 1fr)' }, alignItems: 'start' }}>
      {hasStyles && <Box sx={{ minWidth: 0, maxWidth: hasDimensions ? undefined : 420 }}><WmsStyleControls key={`${node.id}-style`} folder={node.properties.folder} inline /></Box>}
      {hasDimensions && <WmsDimensionControls key={`${node.id}-dimensions`} folder={node.properties.folder} inline horizontal />}
    </Box>
  </Stack>;
};

// The existing dimension controls also drive a portal inside the map's unchanged viewport.
const PinnedTimeline = () => {
  const { pinnedId, setPinnedId } = useContextMenuBase();
  const { owsContext } = useOwsContextBase();
  const { map } = useMapViewerBase();
  const translate = useTranslate();
  const node = pinnedId === undefined ? undefined : owsContext.features.find(feature => feature.id === pinnedId);
  useEffect(() => { if (pinnedId !== undefined && !node) setPinnedId(undefined); }, [pinnedId, node, setPinnedId]);
  if (!map || !node) return null;
  return createPortal(<Paper elevation={6} role="region" aria-label={translate('viewerControls.timeline')}
    ref={(element: HTMLDivElement | null) => { if (element) { DomEvent.disableClickPropagation(element); DomEvent.disableScrollPropagation(element); } }}
    sx={{ position: 'absolute', boxSizing: 'border-box', zIndex: 1100, bottom: 32, left: { xs: 8, sm: 64 }, width: { xs: 'calc(100% - 16px)', sm: 'min(560px, calc(100% - 128px))' }, maxHeight: '45%', overflow: 'auto', p: 1.5, bgcolor: 'background.paper', color: 'text.primary' }}>
    <Stack direction="row" sx={{ alignItems: 'center', gap: 1 }}>
      <Typography variant="subtitle2" noWrap sx={{ flex: 1 }}>{node.properties.title}</Typography>
      <Button size="small" onClick={() => setPinnedId(undefined)}>{translate('viewerControls.unpin')}</Button>
    </Stack>
    <WmsDimensionControls folder={node.properties.folder} inline timeOnly compact />
  </Paper>, map.getContainer());
};

const TreeViews = (
  { 
    initialExpanded = [],
    layers,
    featureTypes
  }: LayerTreeProps
) => {
  const { trees, owsContext, setFeatureActive } = useOwsContextBase()
  // the roots of the trees open as they arrive, so an imported service shows its layers right
  // away; deeper groups stay closed like in a loaded document and open through their arrow. The
  // folders of the leaves keep their state because the drag target of a leaf sits inside it
  const defaultExpandedNodes = useMemo(() => [
    ...owsContext.features
      .filter(feature => (feature.properties.folder ?? '').split('/').filter(Boolean).length === 1)
      .map(feature => feature.properties.folder ?? ''),
    ...owsContext.getLeafNodes().map(feature => feature.properties.folder ?? '')
  ], [owsContext])
  const [expanded, setExpanded] = useState<string[]>([...initialExpanded, ...defaultExpandedNodes])
  // a tree that arrives after the mount - the import of a service or of a stored context - would
  // stay closed with the folders known at the mount; everything that appears later opens up too,
  // while folders the user closed by hand keep their state and removed ones are forgotten
  const knownFolders = useRef(new Set<string>(expanded))
  useEffect(() => {
    const unknown = defaultExpandedNodes.filter(folder => !knownFolders.current.has(folder))
    // folders that are gone are forgotten, so a reimport of a removed tree opens fresh
    knownFolders.current = new Set(defaultExpandedNodes)
    if (unknown.length > 0) {
      setExpanded(prev => [...new Set([...prev, ...unknown])])
    }
  }, [defaultExpandedNodes])

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
    // a registered WFS feature type answers with its database record, like a WMS layer does
    const featureTypeId = node?.getWfsOperationByCode("GetFeature")?.["x-mrmap-feature-type-id"] as Identifier
    const featureTypeRecord = layerRecord === undefined && featureTypeId !== undefined
      ? featureTypes?.find(featureType => featureType.id === featureTypeId)
      : undefined

    return node !== undefined ? (
        <RecordContextProvider
          value={layerRecord ?? featureTypeRecord}
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
      ) : <Fragment></Fragment>
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

TreeItemLabel.displayName = "TreeItemLabel";

const LayerTreeContent = ({
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

  const mrmapFeatureTypes = useMemo(()=>(
    [
      ...new Set(
        owsContext.features
          .map(
            feature =>
              feature.getWfsOperationByCode("GetFeature")?.["x-mrmap-feature-type-id"]
          )
          .filter(Boolean)
      )
    ]
  ),[owsContext])

  const {
    data: featureTypeData,
    refetch: refetchFeatureTypes
  } = useGetMany(
    "FeatureType",
    {
      ids: mrmapFeatureTypes,
      meta: {
        jsonApiParams:{
          'fields[FeatureType]': 'identifier,is_active'
        }
      }
    },
    {
      enabled: mrmapFeatureTypes.length > 0
    }
  )

  const listContext = useMemo(() => {
    const records = [...(Array.isArray(data) ? data : []), ...(Array.isArray(featureTypeData) ? featureTypeData : [])]
    const ids = records.map(d => d.id as Identifier)
    const dataObject: Record<string, RaRecord> = {}
    records.forEach((d: RaRecord) => {
      if (d && d.id !== undefined) dataObject[d.id as Identifier] = d
    })

    return {
      ids,
      data: dataObject,
      total: ids.length,
      page: 1,
      perPage: ids.length || 0,
      loaded: !!data,
      // a refresh answers for both database record kinds the tree shows
      refetch: () => {
        refetch();
        refetchFeatureTypes();
      },
    }
  }, [data, featureTypeData, refetch, refetchFeatureTypes]) as unknown as ListControllerResult

  return (
    <DialogBase>
      <ListContextProvider value={listContext}>
          <TreeViews initialExpanded={initialExpanded} layers={data} featureTypes={featureTypeData} />
          <PinnedTimeline />
          <ContextMenu />
          <Dialog maxWidth="sm"/>
      </ListContextProvider>
    </DialogBase>
  )
}

const LayerTree = (props: LayerTreeProps) => {
  const parent = useContext(LayerControlsContext);
  return parent ? <LayerTreeContent {...props} /> : <ContextMenuBase><LayerTreeContent {...props} /><LayerControlsPanel /></ContextMenuBase>;
};

export default LayerTree
