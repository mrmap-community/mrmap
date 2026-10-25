import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, ButtonProps, RaRecord, useGetOne, useRecordContext, useTranslate } from 'react-admin';
import { useNavigate } from "react-router-dom";

import PublicIcon from '@mui/icons-material/Public';
import { v4 as uuidv4 } from 'uuid';

import { API_BASE_URL } from '../../../../context/HttpClientContext';
import { Authentication } from '../../../../ows-lib/OwsContext/contrib';
import { OWSContext } from '../../../../ows-lib/OwsContext/core';
import { prepareGetCapabilititesUrl } from '../../../../ows-lib/OwsContext/utils';
import { getAuthToken } from '../../../../providers/authProvider';
import { useOwsContextBase } from '../../../../react-ows-lib/ContextProvider/OwsContextBase';



export interface MapViewerButtonProps extends ButtonProps{
  wmsRecord?: RaRecord
  capabilititesUrl?: string
  protocol?: 'WMS' | 'WFS'
}

const MapViewerButton = (
  {
    wmsRecord, 
    capabilititesUrl,
    protocol = 'WMS',
    children,
    ...rest
  }: MapViewerButtonProps
): ReactNode => {
  const navigate = useNavigate();
  const { addWMSByUrl, addWFSByUrl, resetContext, owsContext } = useOwsContextBase()
  const record = useRecordContext({ record: wmsRecord })
  const translate = useTranslate()

  const [getCapaibilitesUrl, setGetCapaibilitesUrl] = useState(
    capabilititesUrl || (protocol === 'WFS' && record?.id !== undefined
      ? new URL(`/mrmap-proxy/wfs/${String(record.id)}?SERVICE=WFS&REQUEST=GetCapabilities&VERSION=2.0.0`, API_BASE_URL).href
      : record?.operationUrls?.find(
      (opUrl: RaRecord) => {
        return (opUrl.method === 1 || opUrl.method === "Get") && (opUrl.operation ===1 || opUrl.operation === "GetCapabilities")
      })?.url)
  )

  const [clicked, setClicked] = useState(false)

  const authHeader = useMemo<Authentication | undefined>(()=>(
    getAuthToken()?.token && getCapaibilitesUrl && (
      new URL(getCapaibilitesUrl).hostname === window.location.hostname ||
      new URL(getCapaibilitesUrl).origin === new URL(API_BASE_URL).origin
    ) ? {
      id: uuidv4(),
      type: "header",
      name: "Authorization",
      value: `Token ${getAuthToken()?.token}`,
      origin: new URL(getCapaibilitesUrl).origin,
    } : undefined
  ),[getCapaibilitesUrl])

  const {data: wmsRecordWithUrl, isLoading, refetch } = useGetOne(
    protocol === 'WFS' ? 'WebFeatureService' : 'WebMapService',
    {
      id: record?.id,
      meta: {
        "jsonApiParams": protocol === 'WFS' ? {
          include: 'featuretypes',
          'fields[WebFeatureService]': 'featuretypes,version',
          'fields[FeatureType]': 'identifier,is_active',
        } : {
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
          if (new URL(operation.href).origin === new URL(getCapaibilitesUrl).origin)
            operation["x-authentication-id"] = authHeader?.id
        })
      })
      const operation = protocol === 'WFS'
        ? feature.getWfsOperationByCode('GetFeature')
        : feature.getWmsOperationByCode("GetMap")
      if (operation !== undefined) {
        operation["x-mrmap-service-id"] = wmsRecordWithUrl?.id
        
        const url = new URL(operation.href)
        const identifier = [...url.searchParams.entries()].find(([key]) =>
          protocol === 'WFS' ? ['typename', 'typenames'].includes(key.toLowerCase()) : key.toLowerCase() === 'layers')?.[1];
        const elements = protocol === 'WFS' ? wmsRecordWithUrl?.featuretypes : wmsRecordWithUrl?.layers;
        const dbLayer = elements?.find((layer: RaRecord) => layer.identifier === identifier)
        if (dbLayer !== undefined){
          const element = protocol === 'WFS' ? 'featuretype' : 'layer';
          operation[`x-mrmap-${element}-id`] = dbLayer?.id
          operation[`x-mrmap-${element}-properties`] = {...dbLayer}
        }
      }
    })
    return context
  }, [wmsRecordWithUrl, protocol, authHeader, getCapaibilitesUrl])

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
    if (!clicked) {
      return
    }
    if (wmsRecordWithUrl === undefined) {
      refetch()
    } else if (getCapaibilitesUrl !== undefined){
      resetContext()
    }
  },[getCapaibilitesUrl, clicked, wmsRecordWithUrl, refetch, resetContext])

  useEffect(() => {
    if (
      clicked && 
      wmsRecordWithUrl !== undefined &&
      owsContext.features.length === 0 && 
      getCapaibilitesUrl !== undefined
    ){
      // Wait until the context is reset before adding the selected service.
      const url = prepareGetCapabilititesUrl(getCapaibilitesUrl, protocol)
      
      const addService = protocol === 'WFS' ? addWFSByUrl : addWMSByUrl;
      addService(
        url.href, 
        authHeader && new Headers({"Authorization": authHeader?.value}), 
        beforeSetHook
      )
      navigate('/viewer')
      setClicked(false)
    }
  }, [clicked, owsContext, getCapaibilitesUrl, wmsRecordWithUrl])

  return (
    <Button
      color="primary"
      onClick={handleOnClick}
      label={translate('ra.action.mapviewer')}
      loading={isLoading}
      disabled={isLoading}
      {...rest}
    >
      {children || <PublicIcon /> }
    </Button>
  )
}

export default MapViewerButton;
