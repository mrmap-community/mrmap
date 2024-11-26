import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren, type ReactNode } from 'react'

import { Point } from 'geojson'
import _ from 'lodash'

import { OWSContext, OWSResource } from '../../ows-lib/OwsContext/core'
import { Position } from '../../ows-lib/OwsContext/enums'
import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'
import { treeify } from '../../ows-lib/OwsContext/utils'

export interface OwsContextBaseType {
  // TODO: crs handling
  //crsIntersection: MrMapCRS[]
  //selectedCrs: MrMapCRS
  //setSelectedCrs: (crs: MrMapCRS) => void
  owsContext: OWSContext
  addWMSByUrl: (url: string) => void
  initialFromOwsContext: (url: string) => void
  trees: TreeifiedOWSResource[]
  activeFeatures: OWSResource[]
  setFeatureActive: (feature: OWSResource, active: boolean) => void
  moveFeature: (source: OWSResource, target: OWSResource, position: Position) => void
}

export const context = createContext<OwsContextBaseType | undefined>(undefined)

export interface OwsContextBaseProps extends PropsWithChildren {
  initialFeatures?: OWSResource[]
}

const copyOWSContext = (owsContext: OWSContext) => {
  return new OWSContext(
    owsContext.id,
    owsContext.features,
    owsContext.bbox,
    owsContext.properties,
    owsContext.capabilititesMap
  )
}

export const OwsContextBase = ({ initialFeatures = [], children }: OwsContextBaseProps): ReactNode => {

  // area of interest in crs 4326
  const [owsContext, setOwsContext] = useState<OWSContext>(new OWSContext(undefined, initialFeatures, undefined, {
    lang: 'en',
    title: 'mrmap ows context',
    updated: new Date().toISOString(),
    display: {}
  },))

  const trees = useMemo(() => {
    return treeify(owsContext.features)
  }, [owsContext])

  const activeFeatures = useMemo(() => {
    return owsContext.getActiveFeatures()
  }, [owsContext])


  const addWMSByUrl = useCallback((url: string) => {
    const request = new Request(url, {
      method: 'GET',
    })
    fetch(request).then(response => response.text()).then(xmlString => {
      const newContext = copyOWSContext(owsContext)
      newContext.appendWms(url, xmlString)
      setOwsContext(newContext)
    }
    )
  }, [owsContext])

  const initialFromOwsContext = useCallback((url: string) => {
    const request = new Request(url, {
      method: 'GET',
    })
    fetch(request).then(response => response.json()).then(async (json: OWSContext) => {
      // todo: check type before setting features.
      // todo: set also other variables
      const newOwsContext = new OWSContext(undefined, json.features.map(feature => new OWSResource(feature.properties, feature.id, feature.bbox, feature.geometry)), json.bbox ?? undefined)
      await newOwsContext.initialize()

      setOwsContext(newOwsContext)
      // TODO: initial map with current display if exists  map?.fitBounds()
    }
    )
  }, [])

  const setFeatureActive = useCallback((feature: OWSResource, active: boolean) => {
    const newContext = copyOWSContext(owsContext)
    newContext.activateFeature(feature, active)
    setOwsContext(newContext)
  }, [owsContext])

  const moveFeature = useCallback((source: OWSResource, target: OWSResource, position: Position = Position.lastChild) => {
    const newContext = copyOWSContext(owsContext)
    newContext.moveFeature(source, target, position)
    setOwsContext(newContext)
  }, [owsContext])


  const updateDisplay = useCallback((size: Point) => {
    const newDisplay = {
      pixelWidth: size.coordinates[0],
      pixelHeight: size.coordinates[1]
    }
    const newContext = copyOWSContext(owsContext)
    newContext.properties.display = newDisplay
    !_.isEqual(owsContext.properties.display, newDisplay) && setOwsContext(newContext)
  }, [owsContext])

  useEffect(() => {
    console.log('owsContext', owsContext)
  }, [owsContext])

  // /** crs handling*/
  // const [selectedCrs, setSelectedCrs] = useState()

  // // intersection of all reference systems
  // const crsIntersection = useMemo(() => {
  //   // TODO: refactor this by using the crs from the ows context resources
  //   // let referenceSystems: MrMapCRS[] = []
  //   /* wmsTrees.map(wms => wms.rootNode?.record.referenceSystems.filter((crs: MrMapCRS) => crs.prefix === 'EPSG')).forEach((_referenceSystems: MrMapCRS[], index) => {
  //     if (index === 0) {
  //       referenceSystems = referenceSystems.concat(_referenceSystems)
  //     } else {
  //       referenceSystems = referenceSystems.filter(crsA => _referenceSystems.some(crsB => crsA.stringRepresentation === crsB.stringRepresentation))
  //     }
  //   }) */
  //   // return referenceSystems
  // }, [owsContext])

  // useEffect(() => {

  //   if (selectedCrs?.bbox !== undefined) {
  //     const bbox = JSON.parse(selectedCrs?.bbox)
  //     const bboxGeoJSON = L.geoJSON(bbox)
  //     const newMaxBounds = bboxGeoJSON.getBounds()
  //     setMaxBounds(newMaxBounds)
  //   }
  // }, [selectedCrs])

  // useEffect(() => {
  //   if (maxBounds !== undefined && map !== undefined) {
  //     const currentCenter = map.getCenter()
  //     map.setMaxBounds(maxBounds)
  //     if (maxBounds.contains(currentCenter)) {
  //       // do nothing... the current center is part of the maximum boundary of the crs system
  //     } else {
  //       // current center is not part of the boundary of the crs system. We need to center the map new
  //       map?.fitBounds(maxBounds)
  //     }

  //     // map?.setMaxBounds(maxBounds)
  //   }
  // }, [map, maxBounds])

  // useEffect(() => {
  //   if (crsIntersection.length > 0 && selectedCrs === undefined) {
  //     const defaultCrs = crsIntersection.find(crs => crs.stringRepresentation === 'EPSG:4326') ?? crsIntersection[0]
  //     setSelectedCrs(defaultCrs)
  //   }
  // }, [crsIntersection, selectedCrs])



  const value = useMemo<OwsContextBaseType>(() => {
    return {
      owsContext,
      addWMSByUrl,
      initialFromOwsContext,
      trees,
      activeFeatures,
      setFeatureActive,
      moveFeature
    }
  }, [
    owsContext,
    addWMSByUrl,
    initialFromOwsContext,
    trees,
    activeFeatures,
    setFeatureActive,
    moveFeature
  ])

  return (
    <context.Provider
      value={value}
    >
      {children}
    </context.Provider>
  )
}

export const useOwsContextBase = (): OwsContextBaseType => {
  const ctx = useContext(context)

  if (ctx === undefined) {
    throw new Error('useOwsContextBase must be inside a OwsContextBase')
  }
  return ctx
}
