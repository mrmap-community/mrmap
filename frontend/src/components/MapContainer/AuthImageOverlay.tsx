import type L from 'leaflet'
import { useEffect, useState } from 'react'
import { ImageOverlay, ImageOverlayProps } from 'react-leaflet'
import { getFeaturesByGetMapUrl } from '../../ows-lib/OwsContext/utils'
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
  const { setFeatureLoadingState, owsContext } = useOwsContextBase()
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [isLoading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    const loadImageWithAuth = async () => {
      try {
        setLoading(true)
        const authOptions = getAuthOptions(auth)

        const response = await fetch(url, {
          headers: authOptions.headers,
          credentials: authOptions.credentials
        })

        if (!response.ok) {
          throw new Error(`Failed to load image: ${response.statusText}`)
        }

        const blob = await response.blob()
        const objectUrl = URL.createObjectURL(blob)
        setImageUrl(objectUrl)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Unknown error'))
        setImageUrl(null)
      } finally {
        setLoading(false)
      }
    }

    loadImageWithAuth()

    // Cleanup object URL on unmount
    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl)
      }
    }
  }, [url, auth])

  useEffect(()=>{
    if (imageUrl !== undefined && imageUrl !== null) {
      const features = getFeaturesByGetMapUrl(new URL(imageUrl), owsContext.features)
      // TODO: this is a bit hacky, we should have a better way to track loading state of features.
      features.forEach(f => setFeatureLoadingState(f, isLoading))
    }
   
  },[isLoading])

  if (isLoading || !imageUrl) {
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
