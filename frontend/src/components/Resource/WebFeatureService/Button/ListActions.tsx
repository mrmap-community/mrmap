import { useRecordContext, useTranslate } from 'react-admin';

import VpnLockIcon from '@mui/icons-material/VpnLock';
import { Tooltip } from '@mui/material';
import { Fragment } from 'react/jsx-runtime';

import WfsMapViewerButton from './MapViewerButton';


const WfsViewerButtons = () => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Fragment>
      <Tooltip title={translate('serviceShow.openMapViewer')}>
        <span><WfsMapViewerButton label="serviceShow.openMapViewer" /></span>
      </Tooltip>
      {record?.isSecured && (
        <Tooltip title={translate('serviceShow.openSecuredMapViewer')}>
          <span>
            <WfsMapViewerButton
              wfsRecord={record}
              capabilititesUrl={record.xmlBackupFileSecured}
              label="serviceShow.openSecuredMapViewer"
            >
              <VpnLockIcon />
            </WfsMapViewerButton>
          </span>
        </Tooltip>
      )}
    </Fragment>
  );
}


export default WfsViewerButtons
