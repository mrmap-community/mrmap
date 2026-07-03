import type { LatLng } from 'leaflet'
import { useMemo, useState } from 'react'
import { Marker, useMapEvent } from 'react-leaflet'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'

const FeatureInfo = (
  
) => {
  const { owsContext } = useOwsContextBase()
  const atomicGetFeatureInfoUrls = useMemo(()=>{
    return owsContext.getOptimizedUrlsByCode(
      "GetFeatureInfo",
      (feature)=>(
        feature.getWmsOperationByCode("GetFeatureInfo")?.active === true
      )
    )
  }, [owsContext])

  const [position, setPosition] = useState<LatLng | null>(null)
  
  useMapEvent('contextmenu', (event) => {
    setPosition(event.latlng)
  })

  return position ? <Marker position={position} /> : null
}

export default FeatureInfo