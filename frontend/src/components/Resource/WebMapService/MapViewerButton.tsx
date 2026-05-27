import PublicIcon from '@mui/icons-material/Public';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
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

  const initialGetCapabilitiesUrl = useRef(capabilititesUrl || record?.operationUrls?.find(
    (opUrl: RaRecord) => {
      return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
    })?.url)
  const [getCapaibilitesUrl, setGetCapaibilitesUrl] = useState()
  const [clicked, setClicked] = useState(false)

  const {data: wmsRecordWithUrl, isLoading, refetch } = useGetOne(
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
    { 
      enabled: false, // Disable automatic query on mount
    }
  )

  const handleOnClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    setClicked(true)
  }, [])

  useEffect(() => {
     const url = wmsRecordWithUrl?.operationUrls?.find(
      (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
      })?.url
      if (url !== undefined){
        setGetCapaibilitesUrl(url)
      }
  },[wmsRecordWithUrl])

  useEffect(() => {
    if (
      clicked && 
      initialGetCapabilitiesUrl.current === undefined && 
      getCapaibilitesUrl !== undefined
    ){
      const url = prepareGetCapabilititesUrl(getCapaibilitesUrl, "wms")
      // todo: how to wait until reset is finished?
      resetContext()
      addWMSByUrl(url.href)
      navigate('/viewer')
      setClicked(false)
    } else if (
      clicked &&
      initialGetCapabilitiesUrl.current === undefined && 
      getCapaibilitesUrl === undefined
    ) {
      refetch()
    }
  },[initialGetCapabilitiesUrl, getCapaibilitesUrl, clicked])

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