import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef } from 'react'

import { ExpandLess, ExpandMore } from '@mui/icons-material'
import { Drawer, type DrawerProps, IconButton } from '@mui/material'

import { type DrawerState, useDrawerContext } from './DrawerContext'

export interface BottomDrawerProps extends DrawerProps {
  aboveComponentId?: string
  height?: string
  callback?: () => void
}

const BottomDrawer = ({
  aboveComponentId,
  callback = () => { },
  children,
  ...rest
}: BottomDrawerProps): ReactNode => {
  const buttonRef = useRef<HTMLButtonElement>(null)

  const { bottomDrawer, setBottomDrawer, rightDrawer, setRightDrawer } = useDrawerContext()
  const lastRightDrawerState = useRef<DrawerState>(rightDrawer)
  const bottomDrawerIsOpenRef = useRef<boolean>(bottomDrawer.isOpen)

  // adjust padding of map div
  useEffect(() => {
    if (aboveComponentId !== undefined) {
      const div: HTMLElement | null = document.querySelector(`#${CSS.escape(aboveComponentId)}`)
      if (div !== undefined && div !== null) {
        if (!bottomDrawer.isOpen) {
          div.style.paddingBottom = '0'
        } else {
          div.style.paddingBottom = bottomDrawer.height
        }
      }
    }
  }, [aboveComponentId, bottomDrawer.height, bottomDrawer.isOpen])

  useEffect(() => {
    // to prevent infinity looping on rightDrawer state change
    if (bottomDrawer.isOpen !== bottomDrawerIsOpenRef.current) {
      bottomDrawerIsOpenRef.current = bottomDrawer.isOpen
      if (bottomDrawer.isOpen) {
        setRightDrawer({ ...rightDrawer, height: `calc(100vh - 50px - ${bottomDrawer.height})` })
      } else {
        setRightDrawer({ ...rightDrawer, height: lastRightDrawerState?.current?.height })
      }
    }
  }, [bottomDrawer.height, bottomDrawer.isOpen, rightDrawer, setRightDrawer])

  const toggleVisible = useCallback(() => {
    setBottomDrawer({ ...bottomDrawer, isOpen: !bottomDrawer.isOpen })
    buttonRef.current?.blur()
    callback()
  }, [bottomDrawer, callback, setBottomDrawer])

  return (
    <>
      <IconButton
        ref={buttonRef}
        color={'inherit'}
        edge="start"
        // className={`rules-drawer-toggle-button ${isVisible ? 'expanded' : 'collapsed'}`}
        onClick={toggleVisible}
        sx={{
          position: 'absolute',
          left: '50%',
          zIndex: 1000,
          padding: 0,
          bottom: `${bottomDrawer.isOpen ? bottomDrawer.height : '0px'}`,
          transition: 'all 225 cubic-bezier(0.4, 0, 0.6, 1) 0ms !important',
          border: 'unset',
          borderRadius: '5px 5px 0 0',
          width: '60px',
          height: '30px',
          color: 'white',
          backgroundColor: '#002140'
        }}
      >
        {bottomDrawer.isOpen ? <ExpandMore /> : <ExpandLess />}
      </IconButton >
      <Drawer
        anchor="bottom"
        open={bottomDrawer.isOpen}
        variant="persistent"
        style={{ top: '100px' }}
        sx={{
          '& .MuiDrawer-paper': {
            height: bottomDrawer.height,
            zIndex: 1001,
            width: bottomDrawer.width,
            marginLeft: bottomDrawer.marginLeft,
            transition: 'all 225ms cubic-bezier(0.4, 0, 0.6, 1) 0ms !important;'
          }
        }}
        {...rest}
      >
        {children ?? bottomDrawer.children}
      </Drawer>
    </>
  )
}

export default BottomDrawer
