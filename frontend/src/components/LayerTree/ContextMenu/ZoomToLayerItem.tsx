import SearchIcon from '@mui/icons-material/Search';
import proj4 from 'proj4';
import { useCallback } from 'react';
import { useTranslate } from 'react-admin';
import { useOwsContextBase } from "../../../react-ows-lib/ContextProvider/OwsContextBase";
import { useMapViewerBase } from '../../MapViewer/MapViewerBase';
import { useContextMenuBase } from "./ContextMenuBase";
import ContextMenuItem from './ContextMenuItem';


const ZoomToLayerItem = () => {
  const { owsContext } = useOwsContextBase()
  const { map } = useMapViewerBase()
  const { node, close } = useContextMenuBase()
  const translate = useTranslate();

  const feature = node?.properties?.folder
    ? owsContext.findResourceByFolder(node.properties.folder)
    : undefined

  const onClick = useCallback(()=>{
    const [minX, minY, maxX, maxY] = feature?.bbox as [
          number,
          number,
          number,
          number
        ]

    const layerCrs = 'EPSG:4326' // feature.properties.referenceSystems?.[0] ?? referenceSystems per layer are not implemented yet

    let sw: [number, number]
    let ne: [number, number]

    if (layerCrs === 'EPSG:4326') {
      sw = [minY, minX]
      ne = [maxY, maxX]
    } else {
      const projection = proj4(layerCrs, 'EPSG:4326')

      const [swLng, swLat] = projection.forward([minX, minY])
      const [neLng, neLat] = projection.forward([maxX, maxY])

      sw = [swLat, swLng]
      ne = [neLat, neLng]
    }
    map?.flyToBounds(
      [sw, ne],
      {
        padding: [20, 20],
        maxZoom: 12,
        duration: 1,
        animate: false,

      }
    )

    close()
  },[feature, close])

  if (!feature?.bbox || feature.bbox.length !== 4) {
    return null
  }

  return (
    <ContextMenuItem
      onClick={onClick}
      icon={<SearchIcon fontSize="small" />}
      label={translate('LayerTree.ContextMenu.zoomToLayer')}
    />
  )
}


export default ZoomToLayerItem