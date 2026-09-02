import VpnLockIcon from '@mui/icons-material/VpnLock';
import { useRecordContext } from 'react-admin';
import MapViewerButton from './MapViewerButton';


const WmsViewerButtons = () => {
  const record = useRecordContext();
  return (
    <div>
      <MapViewerButton />
      {
        record?.isSecured ? 
        <MapViewerButton 
          wmsRecord={record}
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


export default WmsViewerButtons