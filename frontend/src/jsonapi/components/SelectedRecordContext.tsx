import { createContext, type Dispatch, type PropsWithChildren, type SetStateAction, useContext, useMemo, useState } from 'react'
import type { RaRecord } from 'react-admin'

export interface SelectedRecordContextValue {
  selectedRecord: RaRecord | undefined
  setSelectedRecord: Dispatch<SetStateAction<RaRecord | undefined>>
}

const SelectedRecordContext = createContext<SelectedRecordContextValue | undefined>(undefined)

/**
 * The record a screen currently focuses on.
 *
 * A list of records names the record its user clicked, which is what the
 * provider holds. A screen which shows one record throughout - the inspection
 * of one layer of a service - names it with `record` instead, so components
 * which ask for the focused record, like the compact feed of the changelog,
 * scope themselves to it without a click.
 */
export const SelectedRecordContextProvider = ({ children, record }: PropsWithChildren<{ record?: RaRecord }>) => {
  const [selection, setSelectedRecord] = useState<RaRecord>()
  const selectedRecord = record ?? selection
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
