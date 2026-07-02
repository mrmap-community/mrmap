import PublicIcon from '@mui/icons-material/Public';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Button, RaRecord, useGetOne, useRecordContext } from 'react-admin';
import { useNavigate } from "react-router-dom";
import { OWSContext } from '../../../ows-lib/OwsContext/core';
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
  const { addWMSByUrl, resetContext, owsContext } = useOwsContextBase()
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
          "include": "operationUrls,layers",
          "fields[WebMapService]": "operation_urls,version,layers",
          "fields[WebMapServiceOperationUrl]": "url,method,operation",
          "fields[Layer]": "identifier,is_spatial_secured",
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

  const injectMrMapIds = useCallback((context: OWSContext, treeId: number)=>{
    const addedFeatures = context.features.filter(feature => feature.properties.folder?.startsWith(`/${treeId}`))

    addedFeatures.forEach(feature => {
      const operation = feature.getWmsOperationByCode("GetMap")
      if (operation !== undefined) {
        operation["x-mrmap-service-id"] = wmsRecordWithUrl?.id
        
        const url = new URL(operation.href)
        const identifier = [...url.searchParams.entries()].find(([key]) => key.toLowerCase() === 'layers')?.[1];
        const dbLayer = wmsRecordWithUrl?.layers?.find((layer: RaRecord) => layer.identifier === identifier)
        if (dbLayer !== undefined){
          operation["x-mrmap-layer-id"] = dbLayer?.id
        }
      }
    })
    return context
  }, [wmsRecordWithUrl])

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
      (initialGetCapabilitiesUrl.current !== undefined || getCapaibilitesUrl !== undefined)
    ){
      resetContext()
    } else if (
      clicked &&
      initialGetCapabilitiesUrl.current === undefined && 
      getCapaibilitesUrl === undefined
    ) {
      refetch()
    }
  },[initialGetCapabilitiesUrl, getCapaibilitesUrl, clicked])

  useEffect(() => {
    if (
      clicked && 
      owsContext.features.length === 0 && 
      (initialGetCapabilitiesUrl.current !== undefined || getCapaibilitesUrl !== undefined)
    ){
      // wait until context is reset and then add wms by url
      const url = prepareGetCapabilititesUrl(initialGetCapabilitiesUrl.current || getCapaibilitesUrl, "wms")
      addWMSByUrl(url.href, undefined, injectMrMapIds)
      navigate('/viewer')
      setClicked(false)
    }
  }, [clicked, owsContext, getCapaibilitesUrl])

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