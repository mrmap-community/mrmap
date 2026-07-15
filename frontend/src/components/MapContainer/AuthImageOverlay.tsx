import { useQuery } from '@tanstack/react-query'
import type L from 'leaflet'
import { useEffect, useMemo, useState } from 'react'
import { ImageOverlay, ImageOverlayProps } from 'react-leaflet'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'


export interface AuthOptions {
  headers?: Record<string, string>
  credentials?: RequestCredentials
}

export interface AuthImageOverlayProps extends ImageOverlayProps{
  bounds: L.LatLngBounds
  url: string
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

export const AuthImageOverlay = ({
  bounds,
  url,
  interactive = true,
  auth,
  ...rest
}: AuthImageOverlayProps) => {
  const {  owsContext } = useOwsContextBase()
  const [imageUrl, setImageUrl] = useState<string | null>(null)

  const authOptions = useMemo(()=>getAuthOptions(auth),[auth])

  const { data,  isFetching, error } = useQuery({
    queryKey: ['remoteImage'],
    queryFn: () => fetch(url, {
      headers: authOptions.headers,
      credentials: authOptions.credentials
    }).then(r => r.blob()),
  })

  useEffect(() => {
    if (data){
      imageUrl && URL.revokeObjectURL(imageUrl)
      setImageUrl(URL.createObjectURL(data))
    }
    return () => {
      imageUrl && URL.revokeObjectURL(imageUrl)
    }
  }, [data])

  if (isFetching || !imageUrl) {
    return null
  }

  if (error) {
    console.error('AuthImageOverlay error:', error)
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
