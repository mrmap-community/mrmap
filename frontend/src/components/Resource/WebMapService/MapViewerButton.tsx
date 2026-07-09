import PublicIcon from '@mui/icons-material/Public';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, RaRecord, useGetOne, useRecordContext } from 'react-admin';
import { useNavigate } from "react-router-dom";
import { v4 as uuidv4 } from 'uuid';
import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { prepareGetCapabilititesUrl } from '../../../ows-lib/OwsContext/utils';
import { getAuthToken } from '../../../providers/authProvider';
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

  const authHeader = useMemo(()=>({
      id: uuidv4(),
      name: "Authorization",
      value: `Token ${getAuthToken()?.token}`,
    }
  ),[])

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

  const beforeSetHook = useCallback((context: OWSContext, treeId: number)=>{
    
    const authHeaders = Array.isArray(context.authenticationHeaders)
      ? context.authenticationHeaders
      : []
    context.authenticationHeaders = authHeaders
    authHeaders.push(authHeader)
    
    const addedFeatures = context.features.filter(feature => feature.properties.folder?.startsWith(`/${treeId}`))

    addedFeatures.forEach(feature => {
      feature.properties.offerings?.forEach(offering => {
        offering.operations?.forEach(operation => {
          operation["x-authentication-id"] = authHeader.id
        })
      })
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
      
      addWMSByUrl(
        url.href, 
        new Headers({"Authorization": `Token ${authHeader.value}`}), 
        beforeSetHook
      )
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