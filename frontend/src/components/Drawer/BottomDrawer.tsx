import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef } from 'react'

import { ExpandLess, ExpandMore } from '@mui/icons-material'
import { Drawer, type DrawerProps } from '@mui/material'

import { Button, useTheme } from '@mui/material'
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
  const theme = useTheme()

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
        setRightDrawer({ ...rightDrawer, height: `calc(100% - ${bottomDrawer.height})` })
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
    <div
    
      
    >
      <Button
        ref={buttonRef}
        color='info'
        variant='contained'
        size='small'
        onClick={toggleVisible}
        startIcon={bottomDrawer.isOpen ? <ExpandMore /> : <ExpandLess />}
        sx={{
          position: 'absolute',
          left: '50%',
          transform: 'translateX(50%)',
          zIndex: 1000,
          padding: 0,
          bottom: bottomDrawer.isOpen ? `calc(${bottomDrawer.height} + 40px)` : '40px',
          transition: 'all 0.2s cubic-bezier(0.23, 1, 0.32, 1)',
          width: '60px',
          minWidth: '0px',
          height: '25px',
        }}
      >
      </Button >
      <Drawer
        anchor="bottom"
        open={bottomDrawer.isOpen}
        variant="persistent"
        sx={{
          '& .MuiDrawer-paper': {
            height: bottomDrawer.height,
            width: bottomDrawer.width,
            marginLeft: bottomDrawer.marginLeft,
            backgroundColor: theme.palette.background.default,
            bottom: '40px',
          }
        }}
        {...rest}
      >
        {children ?? bottomDrawer.children}
      </Drawer>
    </div>
  )
}

export default BottomDrawer
