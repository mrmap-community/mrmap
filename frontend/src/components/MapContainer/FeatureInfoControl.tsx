import { type LatLng } from 'leaflet'
import { useMemo, useState } from "react"

import { Marker, Popup } from 'react-leaflet'

import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'

const style = {
  position: 'relative',
  //  display: 'flex',
  width: '100%',
  height: 'calc(100vh - 50px)'
  // maxHeight: 'calc(100vh - 50px !important)'
}


const FeatureInfoControl = () => {

  const [featureInfoMarkerPosition, setFeatureInfoMarkerPosition] = useState<LatLng | undefined>(undefined)
  const [featureInfos, setFeatureInfos] = useState<any[]>([])


  const featureInfoAccordions = useMemo(() => featureInfos.map((featureInfoHtml, index) => {
    return <Accordion
      key={index}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        aria-controls={`${index}-content`}
        id={`${index}-header`}
      >
      {index}
      </AccordionSummary>
      <AccordionDetails
        dangerouslySetInnerHTML={{ __html: featureInfoHtml }}
      />
    </Accordion>
  }
  ), [featureInfos])

  const featureInfoMarker = useMemo(() => {
    if (featureInfoMarkerPosition !== undefined && featureInfos.length > 0) {
      return <Marker
          position={featureInfoMarkerPosition}
        >
        <Popup
          minWidth={90}
          eventHandlers={
            {
              remove: () => {
                // setFeatureInfoMarkerPosition(undefined)
                // setFeatureInfos([])
              }
            }
          }
        >
          {featureInfoAccordions}
        </Popup>
      </Marker>
    }
  }, [featureInfoMarkerPosition, featureInfos.length, featureInfoAccordions])


  // useEffect(() => {
  //   if (map !== undefined && map !== null && map !== mapRef.current) {
  //     // map has changed, so we need to pass it through the context
  //     mapRef.current = map
  //     //setMapContext(map)
  //     setSize(map.getContainer().getBoundingClientRect())
  //   }

  //   if (map !== undefined && map !== null && tiles !== undefined && tiles !== tilesRef.current) {
  //     //
  //     // map.on('click dragstart zoom', () => {
  //     //   setFeatureInfos([])
  //     // })
  //     map.removeEventListener('contextmenu')
  //     map.on('contextmenu', (event) => {
  //       const pointRightClick: Point = event.containerPoint
  //       setFeatureInfoMarkerPosition(event.latlng)

  //       const requests = tiles.map(tile => {
  //         const getFeatureinfoUrl = tile.getFeatureinfoUrl
  //         if (getFeatureinfoUrl?.searchParams.get('VERSION') === '1.3.0') {
  //           getFeatureinfoUrl?.searchParams.set('i', Math.round(pointRightClick.x).toString())
  //           getFeatureinfoUrl?.searchParams.set('j', Math.round(pointRightClick.y).toString())
  //         } else {
  //           getFeatureinfoUrl?.searchParams.set('x', Math.round(pointRightClick.x).toString())
  //           getFeatureinfoUrl?.searchParams.set('y', Math.round(pointRightClick.y).toString())
  //         }

  //         getFeatureinfoUrl?.searchParams.set('INFO_FORMAT', 'text/html')

  //         if (getFeatureinfoUrl !== undefined) {
  //           return getFeatureinfoUrl?.href
  //         }
  //         return ''
  //       // eslint-disable-next-line @typescript-eslint/promise-function-async
  //       }).filter(url => url !== '').map((url) => axios.get(url))

  //       const _featureInfos: any[] = []

  //       axios.all(requests).then(
  //         (responses) => {
  //           responses.forEach((response) => {
  //             if (response.data !== undefined) {
  //               _featureInfos.push(response.data)
  //             }
  //           })
  //           setFeatureInfos(_featureInfos)
  //         }
  //       ).catch(reason => { console.log(reason) })
  //     })
  //   }
  // }, [map, tiles])

  return featureInfoMarker
}

export default FeatureInfoControl