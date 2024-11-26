import { useCallback, type ReactNode, type MouseEvent, useState } from 'react'

import { Drawer, type DrawerProps } from '@mui/material'

const ResizeableDrawer = ({ children, ...rest }: DrawerProps): ReactNode => {
  const [isResizing, setIsResizing] = useState<boolean>(false)
  const [lastDownX, setLastDownX] = useState<number>(0)
  const [newWidth, setNewWidth] = useState<number>()

  const hangleMouseMove = useCallback((event: MouseEvent) => {
    if (!isResizing) {
      return
    }

    const offsetRight = document.body.offsetWidth - event.clientX - document.body.offsetLeft
    const minWidth = 50
    const maxWidth = 600
    if (offsetRight > minWidth && offsetRight < maxWidth) {
      setNewWidth(offsetRight)
    }
  }, [])

  const handleMouseDown = useCallback((event: MouseEvent) => {
    setIsResizing(true)
    setLastDownX(event.clientX)
  }, [])

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
  }, [])

  return (
    <Drawer
      onMouseMove={hangleMouseMove}
      PaperProps={{ sx: { width: newWidth } }}
      {...rest}
    >
      <div
        id="dragger"
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        style={{
          width: '5px',

          cursor: 'ew-resize',
          padding: '4px 0 0',
          borderTop: '1px solid #ddd',
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          zIndex: '100',
          backgroundColor: '#f4f7f9'
        }}
      />
      {children}

    </Drawer>
  )
}

export default ResizeableDrawer
