import { createContext, type Dispatch, type PropsWithChildren, type SetStateAction, useContext, useMemo, useState } from 'react'
import type { RaRecord } from 'react-admin'

export interface SelectedRecordContextValue {
  selectedRecord: RaRecord | undefined
  setSelectedRecord: Dispatch<SetStateAction<RaRecord | undefined>>
}

const SelectedRecordContext = createContext<SelectedRecordContextValue | undefined>(undefined)

export const SelectedRecordContextProvider = ({ children }: PropsWithChildren) => {
  const [selectedRecord, setSelectedRecord] = useState<RaRecord>()
  const value = useMemo(() => ({ selectedRecord, setSelectedRecord }), [selectedRecord])

  return (
    <SelectedRecordContext.Provider value={value}>
      {children}
    </SelectedRecordContext.Provider>
  )
}

export const useSelectedRecordContext = (): SelectedRecordContextValue => {
  const context = useContext(SelectedRecordContext)
  if (context === undefined) {
    throw new Error('useSelectedRecordContext must be used inside a SelectedRecordContextProvider')
  }
  return context
}
