import VpnLockIcon from '@mui/icons-material/VpnLock';
import { type ReactNode } from 'react';
import { useRecordContext } from 'react-admin';
import ListGuesser from '../../jsonapi/components/ListGuesser';
import MapViewerButton from '../Resource/WebMapService/MapViewerButton';


const WmsViewerButtons = () => {
  const record = useRecordContext();
  return (
    <div>
      <MapViewerButton />
      {
        record?.isSecured ? 
        <MapViewerButton 
          capabilititesUrl={record?.xmlBackupFileSecured}
          label={'resources.webmapservice.actions.showinviewer.secured'}
        >
          <VpnLockIcon/>
        </MapViewerButton>
        : null
      }


    </div>
  )
}


const WmsList = (): ReactNode => {
    
  return (
    <ListGuesser
      resource='WebMapService'
      additionalActions={<WmsViewerButtons/>}
      sparseFieldsets={[{type: "WebMapService", fields: ["isSecured", "xmlBackupFileSecured"]}]}
    // aside={<TaskList />}
    />

  )
}

export default WmsList
