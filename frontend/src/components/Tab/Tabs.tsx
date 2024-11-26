import { type ReactNode, type SyntheticEvent, useMemo, useCallback } from 'react'

import CancelIcon from '@mui/icons-material/Cancel'
import TabContext from '@mui/lab/TabContext'
import TabList from '@mui/lab/TabList'
import TabPanel from '@mui/lab/TabPanel'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Tab from '@mui/material/Tab'

import { type TabListProps, useTabListContext } from './TabListContext'

export interface TabsProps {
  defaultTabs?: TabListProps[]
}

export const Tabs = ({
  defaultTabs = []
}: TabsProps): ReactNode => {
  const { tabList, setTabList } = useTabListContext()

  const handleChange = useCallback((event: SyntheticEvent, newValue: string): void => {
    setTabList({ ...tabList, activeTab: newValue })
  }, [setTabList, tabList])

  const handleTabClose = useCallback((event, index: number): void => {
    event.stopPropagation()
    const newTabList = tabList
    if (newTabList.tabs.length > 1) {
      newTabList.tabs = newTabList.tabs.splice(index, 1)
    } else {
      newTabList.tabs = []
    }
    setTabList(newTabList)
  }, [setTabList, tabList])

  const tabs = useMemo(() => [...defaultTabs, ...tabList.tabs].map((tabDef, index): ReactNode => (
      <Tab
        key={index}
        value={String(index)}
        {...tabDef.tab}
        icon={tabDef.closeable
          ? <IconButton onClick={(event) => { handleTabClose(event, index) }}>
            <CancelIcon />
          </IconButton>
          : <></>
        }
      />
  )), [defaultTabs, tabList.tabs, handleTabClose])

  const tabPanels = useMemo(() => [...defaultTabs, ...tabList.tabs].map((tabDef, index): ReactNode => (
      <TabPanel key={index} {...tabDef.tabPanel} value={String(index)} />
  )), [defaultTabs, tabList.tabs])

  return (
    <Box sx={{ width: '100%', typography: 'body1' }}>
      <TabContext value={tabList.activeTab === '' ? '0' : tabList.activeTab}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <TabList onChange={handleChange} aria-label="lab API tabs example">
            {...tabs}
          </TabList>
        </Box>
        {...tabPanels}
      </TabContext>
    </Box>
  )
}
