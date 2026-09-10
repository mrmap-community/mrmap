import VpnLockIcon from '@mui/icons-material/VpnLock';
import { useRecordContext } from 'react-admin';
import { Fragment } from 'react/jsx-runtime';
import MapViewerButton from './MapViewerButton';


const WmsViewerButtons = () => {
  const record = useRecordContext();
  return (
    <Fragment>
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


    </Fragment>
  )
}


export default WmsViewerButtons