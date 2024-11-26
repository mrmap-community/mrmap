import { createContext, type Dispatch, type ReactNode, type SetStateAction, useContext, useState, type PropsWithChildren, useEffect } from 'react'

import { type TabPanelProps } from '@mui/lab/TabPanel/TabPanel'
import { type TabProps } from '@mui/material/Tab/Tab'

export interface TabListProps {
  tab: TabProps
  tabPanel: TabPanelProps
  closeable: boolean

}

export interface TabListState {
  activeTab: string
  tabs: TabListProps[]
}

export interface TabsContextType {
  tabList: TabListState
  setTabList: Dispatch<SetStateAction<TabListState>>
}

export const TabsListContext = createContext<TabsContextType | undefined>(undefined)

export const TabListBase = ({ children }: PropsWithChildren): ReactNode => {
  const [tabList, setTabList] = useState<TabListState>({ activeTab: '', tabs: [] })

  return (
    <TabsListContext.Provider
      value={
        {
          tabList,
          setTabList
        }
      }>
      {children}
    </TabsListContext.Provider>
  )
}

export const useTabListContext = (): TabsContextType => {
  const tabListContext = useContext(TabsListContext)
  if (tabListContext === undefined) {
    throw new Error('tabListContext must be inside a TabListBase')
  }
  return tabListContext
}
