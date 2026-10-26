import type { CSSProperties, ReactNode } from 'react'
import { Fragment, useCallback, useEffect, useRef } from 'react'
import { Button, useStore, useTranslate } from 'react-admin'

import { ChevronLeft, ChevronRight, ExpandLess, ExpandMore } from '@mui/icons-material'
import { Drawer as MuiDrawer, type DrawerProps as MuiDrawerProps, useTheme } from '@mui/material'

import { useDrawerContext, type DrawerAnchor, type DrawerState } from './DrawerContext'

export interface DrawerProps extends Omit<MuiDrawerProps, 'anchor' | 'open'> {
  /** Which edge the drawer gathers at; it also decides what the drawer shrinks
   *  for: a right drawer gives up height to open bottom drawers, a bottom
   *  drawer gives up width to open right drawers. */
  anchor: DrawerAnchor
  /** Identifies this instance's persisted state under `mrmap.drawer.<key>`;
   *  two instances must not share one key. */
  instanceKey: string
  /** Visibility and dimensions of a not yet persisted instance. */
  defaults: DrawerState
  /** Id of the container which makes room for the open drawer, e.g. the map. */
  targetId?: string
  /** Runs whenever the layout of this drawer changed, e.g. to re-measure a map. */
  callback?: () => void
}

/** The shared drawer shell of the frontend: one instance per edge, each with
 *  its own persisted visibility and dimensions. Both extents are derived from
 *  the single layout state of the surrounding `DrawerBase`, so opening order
 *  and repeated toggling cannot accumulate or overwrite anything. */
const Drawer = ({
  anchor,
  instanceKey,
  defaults,
  targetId,
  callback = () => { },
  children,
  slotProps,
  ...rest
}: DrawerProps): ReactNode => {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  const theme = useTheme()
  const translate = useTranslate()
  const { drawers, appBarOffset, sidebarOffset, publish, withdraw } = useDrawerContext()
  const [state, setState] = useStore<DrawerState>(`mrmap.drawer.${instanceKey}`, defaults)

  const openInstance = useCallback((open?: boolean) => {
    setState(previous => ({ ...previous, isOpen: open ?? !previous.isOpen }))
    buttonRef.current?.blur()
  }, [setState])

  useEffect(() => {
    publish(instanceKey, {
      anchor,
      isOpen: state.isOpen,
      width: state.width,
      height: state.height,
      open: openInstance
    })
  }, [publish, instanceKey, anchor, state.isOpen, state.width, state.height, openInstance])

  useEffect(() => () => withdraw(instanceKey), [withdraw, instanceKey])

  // The extent every open orthogonal drawer takes away from this one, as a
  // tail of `calc()` subtractions; both drawers derive it from the same
  // registry, so neither constrains the other through state.
  const orthogonalExtent = Object.entries(drawers)
    .filter(([key, other]) => key !== instanceKey && other.anchor !== anchor && other.isOpen)
    .map(([, other]) => ` - ${anchor === 'right' ? other.height : other.width}`)
    .join('')

  const paperStyle: CSSProperties = anchor === 'right'
    ? {
      width: state.width,
      paddingTop: appBarOffset,
      height: `max(0px, calc(100% - ${appBarOffset}${orthogonalExtent}))`
    }
    : {
      height: state.height,
      width: `max(0px, calc(${state.width} - ${sidebarOffset}${orthogonalExtent}))`,
      marginLeft: sidebarOffset,
      bottom: '40px'
    }

  // adjust padding of the adjacent container
  useEffect(() => {
    if (targetId === undefined) {
      return
    }
    const div = document.querySelector<HTMLElement>(`#${CSS.escape(targetId)}`)
    if (!div) {
      return
    }
    const extent = anchor === 'right' ? state.width : state.height
    const setPadding = (value: string) => {
      if (anchor === 'right') {
        div.style.paddingRight = value
      } else {
        div.style.paddingBottom = value
      }
    }
    setPadding(state.isOpen ? extent : '0')
    callbackRef.current()
    return () => {
      setPadding('0')
    }
  }, [anchor, targetId, state.isOpen, state.width, state.height])

  const toggleVisible = useCallback(() => {
    openInstance()
  }, [openInstance])

  const label = translate(`drawer.${state.isOpen ? 'close' : 'open'}${anchor === 'right' ? 'Right' : 'Bottom'}`)
  const toggleIcon = anchor === 'right'
    ? (state.isOpen ? <ChevronRight /> : <ChevronLeft />)
    : (state.isOpen ? <ExpandMore /> : <ExpandLess />)

  return (
    <Fragment>
      <Button
        ref={buttonRef}
        aria-label={label}
        color='info'
        variant='contained'
        size='small'
        onClick={toggleVisible}
        startIcon={toggleIcon}
        sx={anchor === 'right'
          ? {
            position: 'absolute',
            top: '50%',
            zIndex: 1000,
            padding: 0,
            right: state.isOpen ? state.width : '0px',
            transition: 'all 0.2s cubic-bezier(0.23, 1, 0.32, 1)',
            height: '60px',
            minWidth: '0px',
            width: '25px',
          }
          : {
            position: 'absolute',
            left: '50%',
            transform: 'translateX(50%)',
            zIndex: 1000,
            padding: 0,
            bottom: state.isOpen ? `calc(${state.height} + 40px)` : '40px',
            transition: 'all 0.2s cubic-bezier(0.23, 1, 0.32, 1)',
            width: '60px',
            minWidth: '0px',
            height: '25px',
          }
        }
      />

      <MuiDrawer
        anchor={anchor}
        open={state.isOpen}
        variant="persistent"
        slotProps={{
          ...slotProps,
          paper: {
            ...slotProps?.paper,
            style: paperStyle,
          }
        }}
        sx={{
          '& .MuiDrawer-paper': {
            backgroundColor: theme.palette.background.default,
          }
        }}
        {...rest}
      >
        {children}
      </MuiDrawer >
    </Fragment>
  )
}

export default Drawer
