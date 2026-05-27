import PublicIcon from '@mui/icons-material/Public';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Button, RaRecord, useGetOne, useRecordContext } from 'react-admin';
import { useNavigate } from "react-router-dom";
import { prepareGetCapabilititesUrl } from '../../../ows-lib/OwsContext/utils';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

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
  
  const navigate = useNavigate();
  const { addWMSByUrl, resetContext } = useOwsContextBase()
  const record = useRecordContext(wmsRecord)

  const [getCapabilitiesUrl, setGetCapabilitiesUrl] = useState<string | undefined>(capabilititesUrl || record?.operationUrls?.find(
    (opUrl: RaRecord) => {
      return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
    })?.url)

  const [clicked, setClicked] = useState(false)
  
  const {data: wmsRecordWithUrl, isLoading} = useGetOne(
    "WebMapService",
    {
      id: record?.id,
      meta: {
        "jsonApiParams": {
          "include": "operationUrls",
          "fields[WebMapService]": "operation_urls,version",
          "fields[WebMapServiceOperationUrl]": "url,method,operation",
        }
      }
    },
    { enabled: clicked }
  )

  const handleOnClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    if (getCapabilitiesUrl !== undefined){
      const url = prepareGetCapabilititesUrl(getCapabilitiesUrl, "wms")
      resetContext()
      addWMSByUrl(url.href)
      navigate('/viewer')
    } else if (getCapabilitiesUrl === undefined){
      setClicked(true)
    }
        
  }, [getCapabilitiesUrl])

  useEffect(() => {
    if (wmsRecordWithUrl?.operationUrls !== undefined){
      const _getCapabilitiesUrl = wmsRecordWithUrl.operationUrls.find(
        (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
        })?.url
      if (_getCapabilitiesUrl !== undefined && clicked){
        const url = prepareGetCapabilititesUrl(_getCapabilitiesUrl, "wms")
        resetContext()
        addWMSByUrl(url.href)
        navigate('/viewer')
      }
    }
  },[wmsRecordWithUrl])

  return (
    <Button
      color="primary"
      onClick={handleOnClick}
      label={'resources.WebMapService.actions.showInViewer'}
      loading={isLoading}
      disabled={isLoading}
    >
      <PublicIcon />
    </Button>
  )
}

export default MapViewerButton;