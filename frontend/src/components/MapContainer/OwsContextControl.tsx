import { useEffect, useMemo } from 'react'
import { Identifier, RaRecord, useGetMany, useStore } from "react-admin"
import { updateOrAppendSearchParam } from '../../ows-lib/OwsContext/utils'
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase"


const OwsContextControl = () => {
  const { addWMSByUrl } = useOwsContextBase()

  const [pendingWmsList, setPendingWmsList] = useStore<Identifier[]>(`mrmap.mapviewer.append.wms`, [])
  // Separate URLs and IDs
  const { pendingWmsIds, pendingWmsUrls } = useMemo(() => {
    const ids: Identifier[] = []
    const urls: string[] = []
    
    pendingWmsList.forEach(item => {
      if (typeof item === 'string' && (item.startsWith('http://') || item.startsWith('https://'))) {
        urls.push(item)
      } else {
        ids.push(item)
      }
    })
    
    return { pendingWmsIds: ids, pendingWmsUrls: urls }
  }, [pendingWmsList])
  

  const { data: pendingWms } = useGetMany(
    "WebMapService",
    { 
      ids: pendingWmsIds, 
      meta: {
        "jsonApiParams": {
          "include": "operationUrls",
          // FIXME fields are not included if we use sparsefields: "fields[WebMapService]": "operationUrls",
        }
      }
    },
  );

  useEffect(() => {
    // Process direct URLs first
    pendingWmsUrls.forEach(url => {
      addWMSByUrl(url)
    })
    
    // Process fetched WMS objects by ID
    if (pendingWms !== undefined && pendingWms?.length > 0){
      pendingWms.forEach(
        wms => {
          const getCapabilitiesUrl = wms.operationUrls.find(
            (opUrl: RaRecord) => {
              return opUrl.method === "Get" && opUrl.operation === "GetCapabilities"
            })?.url
          if (getCapabilitiesUrl !== undefined){
            const url = new URL(getCapabilitiesUrl)
            const params = url.searchParams
            updateOrAppendSearchParam(params, 'SERVICE', 'WMS')
            updateOrAppendSearchParam(params, 'VERSION', wms.version)
            updateOrAppendSearchParam(params, 'REQUEST', 'GetCapabilities')
           
            addWMSByUrl(url.href)
          }
        }
      )
    }
    
    // Clear the pending list after processing
    if ((pendingWms !== undefined && pendingWms?.length > 0) || pendingWmsUrls.length > 0) {
      setPendingWmsList([])
    }
  }, [pendingWms, pendingWmsUrls])

  return null
}

export default OwsContextControl