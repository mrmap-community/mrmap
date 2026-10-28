import type { PropsWithChildren } from 'react'
import { AdminContext, testDataProvider, useListContext, type ListProps, type RaRecord } from 'react-admin'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, beforeEach, vi } from 'vitest'

import ListGuesser from './ListGuesser'
import { useSelectedRecordContext } from './SelectedRecordContext'

const record = vi.hoisted(() => ({ id: 'selected', title: 'Selected record' }))
const jsonApiQuery = vi.hoisted(() => ({ include: 'service' }))
/** The resource definition and the api the screens below are rendered with. */
const definition = vi.hoisted(() => ({ options: undefined as { list?: Record<string, unknown> } | undefined }))
const client = vi.hoisted(() => ({ api: undefined as { getOperation: (id: string) => unknown } | undefined }))

vi.mock('react-admin', async importOriginal => {
  const actual = await importOriginal<typeof import('react-admin')>()
  return {
    ...actual,
    List: (props: ListProps) => props.disableAuthentication
      ? <actual.List {...props} />
      : <>{props.children}{props.aside}</>,
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
    useResourceDefinition: (props?: { resource?: string }) => ({
      name: props?.resource ?? 'Layer',
      hasShow: false,
      options: definition.options,
    }),
    useSidebarState: () => [false],
    useStore: () => [[], vi.fn()],
  }
})
vi.mock('react-router-dom', () => ({ useParams: () => ({}) }))
vi.mock('../../components/Resource/Generic/History/HistoryList', () => ({ default: () => <span>changelog</span> }))
vi.mock('../../components/Layout/AsideCard', () => ({
  default: ({ children }: PropsWithChildren) => <aside data-testid="changelog-aside">{children}</aside>,
}))
vi.mock('../../components/Lists/CustomListActions', () => ({ default: () => null }))
vi.mock('../../components/Lists/Empty', () => ({ default: () => null }))
vi.mock('../../components/Lists/EmptyWithFilter', () => ({ default: () => null }))
vi.mock('../../context/HttpClientContext', () => ({
  useHttpClientContext: () => ({ api: client.api }),
}))
vi.mock('../hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [{ component: () => <span>Generated title</span>, props: { source: 'title' } }],
}))
vi.mock('../hooks/useFilterInputForOperation', () => ({ useFilterInputForOperation: () => [] }))
vi.mock('../hooks/useJsonApiQuery', () => ({ default: () => jsonApiQuery }))
vi.mock('../hooks/useOnError', () => ({ default: () => undefined }))
vi.mock('../hooks/useResourceSchema', () => ({ default: () => ({ operation: {} }) }))

const SelectedRecordAside = () => {
  const { selectedRecord } = useSelectedRecordContext()
  return <aside>{selectedRecord?.title ?? 'No selection'}</aside>
}

const PreviewAside = () => <span>preview of the selection</span>

beforeEach(() => {
  definition.options = undefined
  client.api = undefined
})

describe('ListGuesser aside of the resource definition', () => {
  it('shows the aside the resource definition names beside its records', () => {
    definition.options = { list: { aside: PreviewAside } }

    render(<ListGuesser />)

    expect(screen.getByText('preview of the selection')).toBeInTheDocument()
  })

  it('keeps the changelog aside of a resource with a historical endpoint below it', () => {
    definition.options = { list: { aside: PreviewAside } }
    client.api = { getOperation: (operationId: string) => (operationId === 'list_HistoricalLayer' ? {} : undefined) }

    render(<ListGuesser />)

    expect(screen.getByText('preview of the selection')).toBeInTheDocument()
    expect(screen.getByTestId('changelog-aside')).toHaveTextContent('changelog')
  })

  it('prefers the aside a screen asks for over the one the definition names', () => {
    definition.options = { list: { aside: PreviewAside } }

    render(<ListGuesser aside={<SelectedRecordAside />} />)

    expect(screen.queryByText('preview of the selection')).toBeNull()
    expect(screen.getByRole('complementary')).toHaveTextContent('No selection')
  })
})

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

describe('ListGuesser related queries', () => {
  it.each([
    { realtime: false, withHeader: false },
    { realtime: true, withHeader: false },
    { realtime: false, withHeader: true },
    { realtime: true, withHeader: true },
  ])('preserves parent scope with custom query options (%j)', async ({ realtime, withHeader }) => {
    const getList = vi.fn().mockResolvedValue({ data: [record], total: 1 })
    const relatedResource = { resource: 'CatalogueService', id: 'catalogue-1' }
    const dataProvider = testDataProvider({
      getList,
      subscribe: vi.fn().mockResolvedValue(undefined),
      unsubscribe: vi.fn().mockResolvedValue(undefined),
    })
    const view = (fields: string) => (
      <AdminContext dataProvider={dataProvider}>
        <ListGuesser
          resource="HarvestingJob"
          relatedResource={relatedResource}
          realtime={realtime}
          header={withHeader ? <ListHeader /> : undefined}
          listContent={<div>Harvesting runs</div>}
          actions={false}
          pagination={false}
          disableSyncWithLocation
          disableAuthentication
          queryOptions={{ meta: { jsonApiParams: { 'fields[HarvestingJob]': fields } } }}
        />
      </AdminContext>
    )
    const { rerender } = render(view('id,phase'))

    await waitFor(() => expect(getList).toHaveBeenCalledWith('HarvestingJob', expect.objectContaining({
      meta: {
        relatedResource,
        jsonApiParams: { include: 'service', 'fields[HarvestingJob]': 'id,phase' },
      },
    })))

    rerender(view('id,phase,progress'))

    await waitFor(() => expect(getList).toHaveBeenLastCalledWith('HarvestingJob', expect.objectContaining({
      meta: {
        relatedResource,
        jsonApiParams: { include: 'service', 'fields[HarvestingJob]': 'id,phase,progress' },
      },
    })))
  })
})

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
