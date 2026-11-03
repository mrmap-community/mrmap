import { RaRecord, useRecordContext, useTranslate } from 'react-admin';

import VpnLockIcon from '@mui/icons-material/VpnLock';
import { ButtonProps, Tooltip } from '@mui/material';
import { Fragment } from 'react/jsx-runtime';

import MapViewerButton from './MapViewerButton';

export interface WmsViewerButtonsProps {
  /** The layer the viewer shall show: it is activated by the buttons, which are asked beside a list
   *  of the elements of a service instead of beside the service itself. */
  element?: RaRecord
  /** The size of the buttons, for a card which is not a row of a grid. */
  size?: ButtonProps['size']
}

/**
 * The buttons which open a web map service in the map viewer: one for the service as it is stored,
 * one for its secured capabilities when the service is secured. An element the caller names is
 * activated in the viewer, which is what lets the aside of a screen of layers ask for the map of the
 * layer its user clicked.
 */
const WmsViewerButtons = ({ element, size }: WmsViewerButtonsProps = {}) => {
  const record = useRecordContext();
  const translate = useTranslate();
  return (
    <Fragment>
      <Tooltip title={translate('serviceShow.openMapViewer')}>
        <span><MapViewerButton element={element} size={size} label="serviceShow.openMapViewer" /></span>
      </Tooltip>
      {record?.isSecured && (
        <Tooltip title={translate('serviceShow.openSecuredMapViewer')}>
          <span>
            <MapViewerButton
              wmsRecord={record}
              capabilititesUrl={record.xmlBackupFileSecured}
              element={element}
              size={size}
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
