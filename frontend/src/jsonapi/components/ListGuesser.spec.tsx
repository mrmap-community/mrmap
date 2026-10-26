import type { PropsWithChildren, ReactElement } from 'react'
import { AdminContext, testDataProvider, useListContext, type RaRecord } from 'react-admin'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ListGuesser from './ListGuesser'
import { useSelectedRecordContext } from './SelectedRecordContext'

const record = vi.hoisted(() => ({ id: 'selected', title: 'Selected record' }))

vi.mock('react-admin', async importOriginal => ({
  ...await importOriginal<typeof import('react-admin')>(),
  List: ({ children, aside }: PropsWithChildren<{ aside?: ReactElement }>) => <>{children}{aside}</>,
  DatagridConfigurable: ({ rowClick, rowSx, children, preferenceKey }: PropsWithChildren<{
    rowClick: (id: string, resource: string, record: RaRecord) => unknown
    rowSx: (record: RaRecord) => { backgroundColor?: unknown }
    preferenceKey: string
  }>) => (
    <>
      <div data-testid="grid-columns" data-preference-key={preferenceKey}>{children}</div>
      <button data-highlighted={Boolean(rowSx(record).backgroundColor)} onClick={() => rowClick(record.id, 'Layer', record)}>Select row</button>
      <button data-highlighted={Boolean(rowSx({ id: 'other' }).backgroundColor)} onClick={() => rowClick('other', 'Layer', { id: 'other', title: 'Other record' })}>Select other row</button>
    </>
  ),
  EditButton: () => null,
  ShowButton: () => null,
  WrapperField: () => null,
  useResourceDefinition: () => ({ name: 'Layer', hasShow: false }),
  useSidebarState: () => [false],
  useStore: () => [[], vi.fn()],
}))
vi.mock('react-router-dom', () => ({ useParams: () => ({}) }))
vi.mock('../../components/Resource/Generic/History/HistoryList', () => ({ default: () => null }))
vi.mock('../../components/Layout/AsideCard', () => ({ default: () => null }))
vi.mock('../../components/Lists/CustomListActions', () => ({ default: () => null }))
vi.mock('../../components/Lists/Empty', () => ({ default: () => null }))
vi.mock('../../components/Lists/EmptyWithFilter', () => ({ default: () => null }))
vi.mock('../../context/HttpClientContext', () => ({ useHttpClientContext: () => ({}) }))
vi.mock('../hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [{ component: () => <span>Generated title</span>, props: { source: 'title' } }],
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

  it('highlights only the selected row and moves the highlight on selection', () => {
    render(<ListGuesser aside={<SelectedRecordAside />} />)
    const first = screen.getByRole('button', { name: 'Select row' })
    const second = screen.getByRole('button', { name: 'Select other row' })
    expect(first).toHaveAttribute('data-highlighted', 'false')
    expect(second).toHaveAttribute('data-highlighted', 'false')

    fireEvent.click(first)
    expect(first).toHaveAttribute('data-highlighted', 'true')
    expect(second).toHaveAttribute('data-highlighted', 'false')

    fireEvent.click(second)
    expect(first).toHaveAttribute('data-highlighted', 'false')
    expect(second).toHaveAttribute('data-highlighted', 'true')
    expect(screen.getByRole('complementary')).toHaveTextContent('Other record')
  })
})

describe('ListGuesser columns', () => {
  it('keeps schema-generated columns by default', () => {
    render(<ListGuesser />)
    expect(screen.getByTestId('grid-columns')).toHaveTextContent('Generated title')
  })

  it('renders explicit columns in order and retains selection', () => {
    render(<ListGuesser
      columns={[<span key="first">Custom first</span>, <span key="second">Custom second</span>]}
      aside={<SelectedRecordAside />}
    />)
    expect(screen.getByTestId('grid-columns')).toHaveTextContent('Custom firstCustom second')
    expect(screen.queryByText('Generated title')).not.toBeInTheDocument()
    expect(screen.getByTestId('grid-columns')).toHaveAttribute('data-preference-key', 'list_Layer.datagrid.customColumns')
    fireEvent.click(screen.getByRole('button', { name: 'Select row' }))
    expect(screen.getByRole('complementary')).toHaveTextContent('Selected record')
  })
})

const ListHeader = () => {
  const { total, setFilters } = useListContext()
  return (
    <header>
      <span>Services: {total}</span>
      <button onClick={() => setFilters({ search: 'example' })}>Search from header</button>
    </header>
  )
}

describe('ListGuesser header', () => {
  it.each([false, true])('shares list state and filters with the header (realtime=%s)', async realtime => {
    const getList = vi.fn().mockResolvedValue({ data: [record], total: 1 })
    render(
      <AdminContext dataProvider={testDataProvider({ getList, subscribe: vi.fn().mockResolvedValue(undefined), unsubscribe: vi.fn().mockResolvedValue(undefined) })}>
        <ListGuesser
          resource="Layer"
          realtime={realtime}
          header={<ListHeader />}
          aside={<aside>Service sidebar</aside>}
          actions={<div>List toolbar</div>}
          debounce={0}
          disableSyncWithLocation
          disableAuthentication
        />
      </AdminContext>
    )

    expect(await screen.findByText('Services: 1')).toBeInTheDocument()
    const header = screen.getByRole('banner')
    const sidebar = screen.getByRole('complementary')
    // The sidebar must sit beside the whole main column, including its header.
    expect(header.parentElement?.parentElement).toBe(sidebar.parentElement)
    expect(header.parentElement).toContainElement(screen.getByText('List toolbar'))
    expect(screen.getByRole('banner').compareDocumentPosition(screen.getByText('List toolbar')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Search from header' }))
    await waitFor(() => expect(getList).toHaveBeenLastCalledWith('Layer', expect.objectContaining({
      filter: { is_update_candidate: false, search: 'example' },
    })))
  })

  it('keeps the header visible when the list is empty', async () => {
    render(
      <AdminContext dataProvider={testDataProvider({ getList: async () => ({ data: [], total: 0 }) })}>
        <ListGuesser
          resource="Layer"
          header={<ListHeader />}
          empty={<div>No services</div>}
          disableSyncWithLocation
          disableAuthentication
        />
      </AdminContext>
    )

    expect(await screen.findByText('No services')).toBeInTheDocument()
    expect(screen.getByText('Services: 0')).toBeInTheDocument()
  })
})
