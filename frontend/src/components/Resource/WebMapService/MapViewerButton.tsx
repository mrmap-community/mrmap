import PublicIcon from '@mui/icons-material/Public';
import Tooltip from '@mui/material/Tooltip';
import { useCallback, type ReactNode } from 'react';
import { Identifier, Link, RaRecord, useRecordContext, useStore, useTranslate } from 'react-admin';

export interface MapViewerButtonProps {
  wmsRecord?: RaRecord
  capabilititesUrl?: string
}

const MapViewerButton = (
  {
    wmsRecord, 
    capabilititesUrl
  }: MapViewerButtonProps
): ReactNode => {
  const record = useRecordContext(wmsRecord)
  const translate = useTranslate();
  const [wmsList, setWmsList] = useStore<Identifier[]>(`mrmap.mapviewer.append.wms`, [])

  const handleOnClick = useCallback(()=>{
    const newWmsList = [...wmsList]
    if (capabilititesUrl !== undefined){
      newWmsList.push(capabilititesUrl)
    }
    if (record !== undefined){
      newWmsList.push(record.id)
    }
    setWmsList(newWmsList)
  }, [wmsList, setWmsList])
  return (
    <Tooltip title={translate('resources.WebMapServic e.actions.showInViewer')}>
      <Link
        to={`/viewer`}
        color="primary"
        onClick={handleOnClick}
        label={translate('resources.WebMapService.actions.showInViewer')}
      >
        <PublicIcon />
        huhu
      </Link>
    </Tooltip>
  )
}

export default MapViewerButton;