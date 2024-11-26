import { OWSContext as IOWSContextCore } from './core'

export interface NamedCRS {
  name: string
  type: "name"
}

export interface LinkedCRS {
  href: string
  type: "proj4"
}

export interface CRS {
  type: "name" | "link"
  properties: NamedCRS | LinkedCRS
}

export interface OWSContext extends IOWSContextCore {
  crs?: CRS // 14-009r1, chapter 7.1: Other possible members are: 1. “crs” - CRS object with a coordinate reference system. However..., we can implement it here as extension as well.

}