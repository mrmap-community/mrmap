import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren, type ReactNode } from 'react'
import { useSidebarState } from 'react-admin'

export type DrawerAnchor = 'right' | 'bottom'

/** The visibility and the configured dimensions of one drawer instance.
 *  Render-time constraints, e.g. from an orthogonal open drawer, are derived
 *  from the layout and never written here, so persisted dimensions survive. */
export interface DrawerState {
  isOpen: boolean
  height: string
  width: string
}

/** What one mounted `Drawer` publishes to the shared layout. */
export interface DrawerInstance {
  anchor: DrawerAnchor
  isOpen: boolean
  width: string
  height: string
  /** Opens the instance or toggles it when `open` stays unanswered. */
  open: (open?: boolean) => void
}

export interface DrawerContextType {
  /** Every mounted drawer instance, keyed by its instance key. */
  drawers: Record<string, DrawerInstance>
  /** Height of the app bar, measured once for all drawers. */
  appBarOffset: string
  /** Width of the react-admin sidebar, which the bottom drawers keep free. */
  sidebarOffset: string
  /** Lets screens such as the layer tree open a drawer by its instance key. */
  openDrawer: (instanceKey: string, open?: boolean) => void
  /** Publishes the state of one mounted drawer; for `Drawer` internals. */
  publish: (instanceKey: string, instance: DrawerInstance) => void
  /** Removes a drawer instance from the layout; for `Drawer` internals. */
  withdraw: (instanceKey: string) => void
}

export const DrawerContext = createContext<DrawerContextType | undefined>(undefined)

/** Provides the layout every `Drawer` instance renders itself from: the other
 *  mounted instances, the app bar height and the sidebar width. It holds no
 *  placement-specific state itself; each drawer persists its own under its
 *  instance key, so any number of instances, even of the same anchor, stay
 *  independent. */
export const DrawerBase = ({ children }: PropsWithChildren): ReactNode => {
  const [drawers, setDrawers] = useState<Record<string, DrawerInstance>>({})
  const [appBarOffset, setAppBarOffset] = useState('0px')
  const [sidebarOpen] = useSidebarState()

  const publish = useCallback((instanceKey: string, instance: DrawerInstance) => {
    setDrawers(previous => {
      const previousInstance = previous[instanceKey]
      if (
        previousInstance &&
        previousInstance.anchor === instance.anchor &&
        previousInstance.isOpen === instance.isOpen &&
        previousInstance.width === instance.width &&
        previousInstance.height === instance.height
      ) {
        return previous
      }
      return { ...previous, [instanceKey]: instance }
    })
  }, [])

  const withdraw = useCallback((instanceKey: string) => {
    setDrawers(previous => {
      const next = { ...previous }
      delete next[instanceKey]
      return next
    })
  }, [])

  const openDrawer = useCallback((instanceKey: string, open?: boolean) => {
    drawers[instanceKey]?.open(open)
  }, [drawers])

  useEffect(() => {
    const appBar = document.querySelector<HTMLElement>('.MuiAppBar-root, header[role="banner"]')
    if (!appBar || typeof ResizeObserver === 'undefined') {
      return
    }

    const updateAppBarOffset = () => {
      setAppBarOffset(`${Math.round(appBar.getBoundingClientRect().height)}px`)
    }

    updateAppBarOffset()

    const resizeObserver = new ResizeObserver(updateAppBarOffset)
    resizeObserver.observe(appBar)

    window.addEventListener('resize', updateAppBarOffset)

    return () => {
      resizeObserver.disconnect()
      window.removeEventListener('resize', updateAppBarOffset)
    }
  }, [])

  const value = useMemo<DrawerContextType>(() => ({
    drawers,
    appBarOffset,
    sidebarOffset: sidebarOpen ? '250px' : '58px',
    openDrawer,
    publish,
    withdraw
  }), [drawers, appBarOffset, sidebarOpen, openDrawer, publish, withdraw])

  return (
    <DrawerContext.Provider value={value}>
      {children}
    </DrawerContext.Provider>
  )
}

export const useDrawerContext = (): DrawerContextType => {
  const drawerContext = useContext(DrawerContext)
  if (drawerContext === undefined) {
    throw new Error('drawerContext must be inside a DrawerBase')
  }
  return drawerContext
}

