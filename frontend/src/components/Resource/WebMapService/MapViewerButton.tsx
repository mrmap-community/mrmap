import PublicIcon from '@mui/icons-material/Public';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, ButtonProps, RaRecord, useGetOne, useRecordContext } from 'react-admin';
import { useNavigate } from "react-router-dom";
import { v4 as uuidv4 } from 'uuid';
import { Authentication } from '../../../ows-lib/OwsContext/contrib';
import { OWSContext } from '../../../ows-lib/OwsContext/core';
import { prepareGetCapabilititesUrl } from '../../../ows-lib/OwsContext/utils';
import { getAuthToken } from '../../../providers/authProvider';
import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';



export interface MapViewerButtonProps extends ButtonProps{
  wmsRecord?: RaRecord
  capabilititesUrl?: string
}

const MapViewerButton = (
  {
    wmsRecord, 
    capabilititesUrl,
    children,
    ...rest
  }: MapViewerButtonProps
): ReactNode => {
  const navigate = useNavigate();
  const { addWMSByUrl, resetContext, owsContext } = useOwsContextBase()
  const record = useRecordContext(wmsRecord)

  const [getCapaibilitesUrl, setGetCapaibilitesUrl] = useState(
    capabilititesUrl || record?.operationUrls?.find(
      (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
      })?.url
  )

  const [clicked, setClicked] = useState(false)

  const authHeader = useMemo<Authentication | undefined>(()=>(
    getCapaibilitesUrl && new URL(getCapaibilitesUrl).hostname === window.location.hostname ? {
      id: uuidv4(),
      type: "header",
      name: "Authorization",
      value: `Token ${getAuthToken()?.token}`,
    } : undefined
  ),[getCapaibilitesUrl])

  const {data: wmsRecordWithUrl, isLoading, refetch } = useGetOne(
    "WebMapService",
    {
      id: record?.id,
      meta: {
        "jsonApiParams": {
          "include": "operationUrls,layers",
          "fields[WebMapService]": "operation_urls,version,layers",
          "fields[WebMapServiceOperationUrl]": "url,method,operation",
          "fields[Layer]": "identifier,is_spatial_secured,is_active",
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
    if (authHeader !== undefined) {
      const authHeaders = Array.isArray(context.authenticationHeaders) 
      ? context.authenticationHeaders
      : []
      context.authenticationHeaders = authHeaders
      authHeaders.push(authHeader)
    }
    
    const addedFeatures = context.features.filter(feature => feature.properties.folder?.startsWith(`/${treeId}`))

    addedFeatures.forEach(feature => {
      authHeader && feature.properties.offerings?.forEach(offering => {
        offering.operations?.forEach(operation => {
          operation["x-authentication-id"] = authHeader?.id
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
          operation["x-mrmap-layer-properties"] = {...dbLayer}
        }
      }
    })
    return context
  }, [wmsRecordWithUrl])

  useEffect(() => {
    if (capabilititesUrl !== undefined) {
      // url is allready set by props
      return
    }
     const url = wmsRecordWithUrl?.operationUrls?.find(
      (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
      })?.url
      if (url !== undefined && getCapaibilitesUrl === undefined){
        setGetCapaibilitesUrl(url)
      }
  },[wmsRecordWithUrl])

  useEffect(() => {
    if (
      (clicked &&
      getCapaibilitesUrl === undefined) ||
      wmsRecordWithUrl === undefined
    ) {
      refetch()
    } else if (
      clicked && 
      getCapaibilitesUrl !== undefined
    ){
      resetContext()
    }
  },[getCapaibilitesUrl, clicked])

  useEffect(() => {
    if (
      clicked && 
      owsContext.features.length === 0 && 
      getCapaibilitesUrl !== undefined
    ){
      // wait until context is reset and then add wms by url
      const url = prepareGetCapabilititesUrl(getCapaibilitesUrl, "wms")
      
      addWMSByUrl(
        url.href, 
        authHeader && new Headers({"Authorization": authHeader?.value}), 
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
      {...rest}
    >
      {children || <PublicIcon />} 
    </Button>
  )
}

export default MapViewerButton;