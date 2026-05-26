import { type ReactNode } from 'react'
import ListGuesser from '../../jsonapi/components/ListGuesser'
import MapViewerButton from '../Resource/WebMapService/MapViewerButton'



const WmsList = (): ReactNode => {
  return (
    <ListGuesser
      resource='WebMapService'
      additionalActions={<MapViewerButton />}
    // aside={<TaskList />}
    />

  )
}

export default WmsList
