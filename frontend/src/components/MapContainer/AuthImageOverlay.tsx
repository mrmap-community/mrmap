import { useQuery } from '@tanstack/react-query'
import type L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ImageOverlay, ImageOverlayProps } from 'react-leaflet'
import { OptimizedUrlsMap } from '../../ows-lib/OwsContext/core'
import { useMapViewerBase } from '../MapViewer/MapViewerBase'


export interface AuthOptions {
  headers?: Record<string, string>
  credentials?: RequestCredentials
}

export interface AuthImageOverlayProps extends Partial<ImageOverlayProps>{
  bounds: L.LatLngBounds
  optimiuedUrl: OptimizedUrlsMap
  interactive?: boolean
  auth?: AuthOptions | (() => AuthOptions) | Headers
}

/**
 * Converts Headers object to Record<string, string>
 */
const headersToObject = (headers?: Headers): Record<string, string> => {
  if (!headers) return {}
  const obj: Record<string, string> = {}
  headers.forEach((value, key) => {
    obj[key] = value
  })
  return obj
}

/**
 * Gets authentication options. Supports:
 * 1. Explicit auth object
 * 2. Auth function that returns auth options
 * 3. Headers object that gets converted to auth options
 */
const getAuthOptions = (auth?: AuthOptions | (() => AuthOptions) | Headers): AuthOptions => {
  // If auth is a function, call it
  if (typeof auth === 'function') {
    return auth()
  }

  // If auth is a Headers object, convert it
  if (auth instanceof Headers) {
    return {
      headers: headersToObject(auth)
    }
  }

  // If auth is an object, return it
  if (auth) {
    return auth
  }
  return {}
}

const getServiceExceptionMessage = (xml: string): string | undefined => {
  if (!xml.trimStart().startsWith('<')) return undefined

  try {
    const document = new DOMParser().parseFromString(xml, 'application/xml')
    const exception = Array.from(document.getElementsByTagName('*'))
      .find((element) => element.localName === 'ServiceException')

    if (!exception) return undefined

    const code = exception.getAttribute('code')
    const message = exception.textContent?.trim()

    if (code && message) return `${code}: ${message}`
    return message || code || 'OGC service exception'
  } catch {
    return undefined
  }
}

export const AuthImageOverlay = ({
  bounds,
  optimiuedUrl,
  interactive = true,
  auth,
  ...rest
}: AuthImageOverlayProps) => {
  
  const { reportMapLoading, removeMapLoading } = useMapViewerBase()
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const startedAt = useRef(performance.now())

  const authOptions = useMemo(()=>getAuthOptions(auth),[auth])
  const url = optimiuedUrl.url.href

  const loadingId = `image:${url}`

  const { data, isFetching, error } = useQuery({
    queryKey: ['remoteImage', url, authOptions.headers, authOptions.credentials],
    retry: false,
    retryOnMount: false,
    queryFn: async () => {
      const response = await fetch(url, {
        headers: authOptions.headers,
        credentials: authOptions.credentials
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const blob = await response.blob()
      const serviceExceptionMessage = getServiceExceptionMessage(await blob.text())
      if (serviceExceptionMessage) {
        throw new Error(serviceExceptionMessage)
      }

      return blob
    },
  })

  useEffect(() => {
    const timing = performance.now() - startedAt.current
    if (isFetching) {
      reportMapLoading(loadingId, 'loading')
    } else if (error) {
      const mapError = {
        message: error instanceof Error ? error.message : String(error),
        features: optimiuedUrl.features
      }
      reportMapLoading(loadingId, 'error', mapError, timing)
    } else if (data) {
      reportMapLoading(loadingId, 'ready', undefined, timing)
    }
  }, [data, error, isFetching, loadingId, reportMapLoading])

  useEffect(() => {
    return () => removeMapLoading(loadingId)
  }, [loadingId, removeMapLoading])

  useEffect(() => {
    if (!data) {
      setImageUrl(null)
      return
    }

    const nextImageUrl = URL.createObjectURL(data)
    setImageUrl(nextImageUrl)

    return () => {
      URL.revokeObjectURL(nextImageUrl)
    }
  }, [data])


  if (error) {
    return null
  }

  if (isFetching || !imageUrl) {
    return null
  }

  return (
    <ImageOverlay
      bounds={bounds}
      url={imageUrl}
      interactive={interactive}
      {...rest}
    />
  )
}
