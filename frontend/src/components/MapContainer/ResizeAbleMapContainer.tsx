import useResizeObserver from "@react-hook/resize-observer"
import { useEffect, useRef, useState } from "react"
import { useMap } from "react-leaflet"



const AutoResizeMapContainer = () => {

  const [size, setSize] = useState<DOMRectReadOnly>()
  const sizeRef = useRef<DOMRectReadOnly>()

  const map = useMap()

  useResizeObserver(map?.getContainer() ?? null, (entry) => { setSize(entry.contentRect) })
  
  useEffect(() => {
    // on every size change, we need to tell the map context to invalidate the old size values.
    // Otherwise the getSize() will not provide correct information about the current map container size
    if (size !== undefined && map !== undefined && map !== null && size !== sizeRef.current) {
      sizeRef.current = size
      map.invalidateSize()
    }
  }, [size, map])

  return (null)
}

export default AutoResizeMapContainer