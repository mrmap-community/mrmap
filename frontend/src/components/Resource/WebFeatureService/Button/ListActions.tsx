import { RaRecord, useRecordContext, useTranslate } from 'react-admin';

import VpnLockIcon from '@mui/icons-material/VpnLock';
import { ButtonProps, Tooltip } from '@mui/material';
import { Fragment } from 'react/jsx-runtime';

import WfsMapViewerButton from './MapViewerButton';

export interface WfsViewerButtonsProps {
  /** The feature type the viewer shall show: it is the one type the viewer asks for, which is asked
   *  beside a list of the feature types of a service instead of beside the service itself. */
  element?: RaRecord
  /** The size of the buttons, for a card which is not a row of a grid. */
  size?: ButtonProps['size']
}

/**
 * The buttons which open a web feature service in the map viewer: one for the service as it is
 * stored, one for its secured capabilities when the service is secured. A feature type the caller
 * names is the one type the viewer asks for, which is what lets the aside of a screen of feature
 * types ask for the map of the type its user clicked.
 */
const WfsViewerButtons = ({ element, size }: WfsViewerButtonsProps = {}) => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Fragment>
      <Tooltip title={translate('serviceShow.openMapViewer')}>
        <span><WfsMapViewerButton element={element} size={size} label="serviceShow.openMapViewer" /></span>
      </Tooltip>
      {record?.isSecured && (
        <Tooltip title={translate('serviceShow.openSecuredMapViewer')}>
          <span>
            <WfsMapViewerButton
              wfsRecord={record}
              capabilititesUrl={record.xmlBackupFileSecured}
              element={element}
              size={size}
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
