import { fireEvent, render, screen } from '@testing-library/react'
import type { PropsWithChildren, ReactElement } from 'react'
import type { RaRecord } from 'react-admin'
import { describe, expect, it, vi } from 'vitest'
import ListGuesser from './ListGuesser'
import { useSelectedRecordContext } from './SelectedRecordContext'

const record = vi.hoisted(() => ({ id: 'selected', title: 'Selected record' }))

vi.mock('react-admin', () => ({
  List: ({ children, aside }: PropsWithChildren<{ aside?: ReactElement }>) => <>{children}{aside}</>,
  DatagridConfigurable: ({ rowClick }: { rowClick: (id: string, resource: string, record: RaRecord) => unknown }) => (
    <button onClick={() => rowClick(record.id, 'Layer', record)}>Select row</button>
  ),
  EditButton: () => null,
  ShowButton: () => null,
  WrapperField: () => null,
  useResourceDefinition: () => ({ name: 'Layer', hasShow: false }),
  useSidebarState: () => [false],
  useStore: () => [[], vi.fn()],
}))
vi.mock('react-router-dom', () => ({ useParams: () => ({}) }))
vi.mock('../../components/HistoryList', () => ({ default: () => null }))
vi.mock('../../components/Layout/AsideCard', () => ({ default: () => null }))
vi.mock('../../components/Lists/CustomListActions', () => ({ default: () => null }))
vi.mock('../../components/Lists/Empty', () => ({ default: () => null }))
vi.mock('../../components/Lists/EmptyWithFilter', () => ({ default: () => null }))
vi.mock('../../context/HttpClientContext', () => ({ useHttpClientContext: () => ({}) }))
vi.mock('../hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [{ component: () => null, props: { source: 'title' } }],
}))
vi.mock('../hooks/useFilterInputForOperation', () => ({ useFilterInputForOperation: () => [] }))
vi.mock('../hooks/useJsonApiQuery', () => ({ default: () => ({}) }))
vi.mock('../hooks/useOnError', () => ({ default: () => undefined }))
vi.mock('../hooks/useResourceSchema', () => ({ default: () => ({ operation: {} }) }))
vi.mock('./Realtime/RealtimeList', () => ({ default: () => null }))

const SelectedRecordAside = () => {
  const { selectedRecord } = useSelectedRecordContext()
  return <aside>{selectedRecord?.title ?? 'No selection'}</aside>
}

describe('ListGuesser selected record', () => {
  it('shares the clicked row with a custom aside and calls onRowClick', () => {
    const onRowClick = vi.fn()
    render(<ListGuesser aside={<SelectedRecordAside />} onRowClick={onRowClick} />)

    expect(screen.getByRole('complementary')).toHaveTextContent('No selection')
    fireEvent.click(screen.getByRole('button', { name: 'Select row' }))

    expect(screen.getByRole('complementary')).toHaveTextContent('Selected record')
    expect(onRowClick).toHaveBeenCalledExactlyOnceWith(record)
  })
})
