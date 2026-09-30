import type { Polygon } from 'geojson'

import { Fragment, type PropsWithChildren, type ReactNode } from 'react'

import { FormGroup } from '@mui/material'

import { useMapViewerBase } from './MapViewerBase'


export interface DisplayPositionProps {
  crsBbox?: Polygon
}

const DisplayPosition = ({
  crsBbox
}: DisplayPositionProps): ReactNode => {

  const { featureCollection } = useMapViewerBase()


  return (
    <FormGroup>
      <Fragment>
        Current Boundary:
        {featureCollection}
      </Fragment>
    </FormGroup>
  )
}


const MapSettingsEditor = ({ children }: PropsWithChildren): ReactNode => {
  const { selectedCrs, setSelectedCrs } = useMapViewerBase()

  //const { crsIntersection, selectedCrs, setSelectedCrs } = useOwsContextBase()

  //const [crs, setCrs] = useState<string>(selectedCrs?.stringRepresentation ?? 'EPSG:4326')

  // const menuItems = useMemo(()=>{
  //   if (crsIntersection?.length > 0){
  //     return crsIntersection.map(crs => <MenuItem key={crs.stringRepresentation} value={crs.stringRepresentation}>{crs.stringRepresentation}</MenuItem>)
  //   } else {
  //     return [<MenuItem key={'EPSG:4326'} value={'EPSG:4326'}>EPSG:4326</MenuItem>]
  //   }
  // },[crsIntersection])

  // useEffect(() => {
  //   if (crs !== undefined) {
  //     const newCrs = crsIntersection.find(_crs => _crs.stringRepresentation === crs)
  //     if (newCrs !== undefined) {
  //       setSelectedCrs(newCrs)
  //     }
  //   }
  // }, [crs, crsIntersection, setSelectedCrs])


  return (
      <Fragment>
        <DisplayPosition/>

        {/* <Select
            labelId="crs-select-label"
            id="crs-simple-select"
            value={crs}
            defaultValue='EPSG:4326'
            label="Reference System"
            onChange={(event) => { setCrs(event.target.value) }}
        >
            {...menuItems}
        </Select> */}
      </Fragment>
  )
}

export default MapSettingsEditor

