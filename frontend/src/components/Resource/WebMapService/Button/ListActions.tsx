import VpnLockIcon from '@mui/icons-material/VpnLock';
import { Tooltip } from '@mui/material';
import { useRecordContext, useTranslate } from 'react-admin';
import { Fragment } from 'react/jsx-runtime';
import MapViewerButton from './MapViewerButton';


const WmsViewerButtons = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Fragment>
      <Tooltip title={translate('serviceShow.openMapViewer')}>
        <span><MapViewerButton label="serviceShow.openMapViewer" /></span>
      </Tooltip>
      {record?.isSecured && (
        <Tooltip title={translate('serviceShow.openSecuredMapViewer')}>
          <span>
            <MapViewerButton
              wmsRecord={record}
              capabilititesUrl={record.xmlBackupFileSecured}
              label="serviceShow.openSecuredMapViewer"
            >
              <VpnLockIcon />
            </MapViewerButton>
          </span>
        </Tooltip>
      )}


    </Fragment>
  )
}


export default WmsViewerButtons
