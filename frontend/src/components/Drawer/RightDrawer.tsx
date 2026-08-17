import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { ChevronLeft, ChevronRight } from '@mui/icons-material'
import { Drawer, useTheme, type DrawerProps } from '@mui/material'

import { Button } from 'react-admin'
import { useDrawerContext } from './DrawerContext'


export interface RightDrawerProps extends DrawerProps {
  leftComponentId?: string
  callback?: () => void
}

const RightDrawer = ({
  leftComponentId,
  callback = () => { },
  children,
  ...rest
}: RightDrawerProps): ReactNode => {
  const buttonRef = useRef<HTMLButtonElement>(null)

  const { rightDrawer, setRightDrawer } = useDrawerContext()
  const [appBarOffset, setAppBarOffset] = useState('0px')
  const theme = useTheme()
  useEffect(() => {
    const appBar = document.querySelector<HTMLElement>('.MuiAppBar-root, header[role="banner"]')

    if (!appBar) {
      setAppBarOffset('0px')
      return
    }

    const updateAppBarOffset = () => {
      const height = Math.round(appBar.getBoundingClientRect().height)
      setAppBarOffset(`${height}px`)
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

  const drawerHeight = rightDrawer.height === '100%' ? '100%' : `calc(${rightDrawer.height} - ${appBarOffset})`

  // adjust padding of map div
  useEffect(() => {
    if (leftComponentId !== undefined) {
      const div: any = document.querySelector(`#${CSS.escape(leftComponentId)}`)
      if (!rightDrawer.isOpen) {
        div.style.paddingRight = '0'
      } else {
        div.style.paddingRight = rightDrawer.width
      }
    }
  }, [leftComponentId, rightDrawer.isOpen, rightDrawer.width])

  const toggleVisible = useCallback(() => {
    setRightDrawer({ ...rightDrawer, isOpen: !rightDrawer.isOpen })
    buttonRef.current?.blur()
    callback()
  }, [setRightDrawer, rightDrawer, callback])

  return (
    <div>
      <Button
        ref={buttonRef}
        color='primary'
        size='large'
        onClick={toggleVisible}
        sx={{
          position: 'absolute',
          top: '50%',
          zIndex: 1000,
          padding: 0,
          right: `${rightDrawer.isOpen ? rightDrawer.width : '0px'}`,
          transition: 'all 0.2s cubic-bezier(0.23, 1, 0.32, 1)',
          //width: '30px',
          height: '60px',
          backgroundColor: theme.palette.background.paper
        }
        }
      >
        {rightDrawer.isOpen ? <ChevronRight /> : <ChevronLeft />}
      </Button >

      <Drawer
        anchor="right"
        open={rightDrawer.isOpen}
        variant="persistent"
        sx={
          {
            '& .MuiDrawer-paper': {
              width: rightDrawer.width,
              top: appBarOffset,
              height: drawerHeight,
              backgroundColor: theme.palette.background.default
            }
          }
        }
        {...rest}
      >
        {children ?? rightDrawer.children}
      </Drawer >

    </div>
  )
}

export default RightDrawer
