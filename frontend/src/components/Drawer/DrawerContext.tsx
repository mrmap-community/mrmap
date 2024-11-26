import { createContext, type Dispatch, type ReactNode, type SetStateAction, useContext, useState, type PropsWithChildren, useEffect } from 'react'
import { useSidebarState } from 'react-admin'
import { useStore } from 'react-admin'

export interface DrawerState {
  isOpen: boolean
  height: string
  width: string
  marginLeft?: string
  children?: ReactNode
}

export interface DrawerContextType {
  rightDrawer: DrawerState
  setRightDrawer: Dispatch<SetStateAction<DrawerState>>
  bottomDrawer: DrawerState
  setBottomDrawer: Dispatch<SetStateAction<DrawerState>>
}

export const DrawerContext = createContext<DrawerContextType | undefined>(undefined)

export const DrawerBase = ({ children }: PropsWithChildren): ReactNode => {
  const [open] = useSidebarState()
  const [lastOpenState, setLastOpenState] = useState<boolean>()

  const [rightDrawer, setRightDrawer] = useStore<DrawerState>('mrmap.drawer.rightdrawer', { isOpen: false, height: 'calc(100vh - 50px)', width: '20vw' });
  const [bottomDrawer, setBottomDrawer] = useStore<DrawerState>('mrmap.drawer.bottomdrawer', { isOpen: false, height: '30vh', width: '100vw', marginLeft: `${open ? '250px' : '58px'}` })

  useEffect(() => {
    if (lastOpenState === undefined || (open !== lastOpenState)) {
      setLastOpenState(open)
      setBottomDrawer({ ...bottomDrawer, marginLeft: `${open ? '250px' : '58px'}` })
    }
  }, [open])

  return (
    <DrawerContext.Provider
      value={
        {
          rightDrawer,
          setRightDrawer,
          bottomDrawer,
          setBottomDrawer
        }
      }>
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
