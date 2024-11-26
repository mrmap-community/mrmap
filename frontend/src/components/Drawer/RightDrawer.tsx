import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef } from 'react'

import { ChevronLeft, ChevronRight } from '@mui/icons-material'
import { Drawer, type DrawerProps, IconButton } from '@mui/material'

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
    <>
      <IconButton
        ref={buttonRef}
        color={'inherit'}
        edge="start"
        // className={`rules-drawer-toggle-button ${isVisible ? 'expanded' : 'collapsed'}`}
        onClick={toggleVisible}
        sx={{
          position: 'absolute',
          top: '50%',
          zIndex: 1000,
          padding: 0,
          right: `${rightDrawer.isOpen ? rightDrawer.width : '0px'}`,
          transition: 'all 0.2s cubic-bezier(0.23, 1, 0.32, 1)',
          border: 'unset',
          borderRadius: '5px 0 0 5px',
          width: '30px',
          height: '60px',
          color: 'white',
          backgroundColor: '#002140'
        }
        }

      >
        {rightDrawer.isOpen ? <ChevronRight /> : <ChevronLeft />}
      </IconButton >

      <Drawer
        anchor="right"
        open={rightDrawer.isOpen}
        variant="persistent"
        style={{ top: '100px' }}
        sx={
          {
            '& .MuiDrawer-paper': {
              width: rightDrawer.width,
              zIndex: 1000,
              top: '50px',
              height: rightDrawer.height
              // padding: `${theme.spacing(0, 1)}`,
              // justifyContent: 'flex-start'
            }
          }
        }
        {...rest}
      >
        {children ?? rightDrawer.children}
      </Drawer >

    </>
  )
}

export default RightDrawer
