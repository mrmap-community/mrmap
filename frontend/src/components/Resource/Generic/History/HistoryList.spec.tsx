import { AdminContext, ResourceContextProvider, testDataProvider } from 'react-admin'
import { MemoryRouter } from 'react-router-dom'

import { QueryClient } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import polyglotI18nProvider from 'ra-i18n-polyglot'
import { describe, expect, it, vi } from 'vitest'

import en from '../../../../i18n/en'
import { SelectedRecordContextProvider, useSelectedRecordContext } from '../../../../jsonapi/components/SelectedRecordContext'
import HistoryList from './HistoryList'
import { historicalSource } from './historySources'

// this screen renders full react-admin lists and dialogs and needs more than the default timeout
vi.setConfig({ testTimeout: 20000 })

const events = [
  { id: 'multi', title: 'Weather service', historyType: 'updated', historyDate: '2026-10-07T12:15:00Z', historyUser: { username: 'alice' }, delta: [
    { field: 'title', old: 'Old title', new: 'New title' },
    { field: 'abstract', old: 'Old abstract', new: 'New abstract' },
    { field: 'service_url', old: 'https://old.example.com', new: 'https://new.example.com' },
  ] },
  { id: 'single', title: 'Weather service', historyType: 'updated', historyDate: '2026-10-07T12:10:38Z', historyUser: null, delta: [{ field: 'is_active', old: false, new: true }] },
  { id: 'deleted', title: 'Weather service', historyType: 'deleted', historyDate: '2026-10-07T11:00:00Z', historyUser: null, delta: [{ field: 'title', old: 'Old title', new: null }] },
]

const Selection = () => {
  const { setSelectedRecord } = useSelectedRecordContext()
  return <button onClick={() => setSelectedRecord({ id: 'service', title: 'Weather service' })}>Select service</button>
}

const renderHistory = (getList = vi.fn().mockResolvedValue({ data: events, total: events.length })) => {
  const result = render(
    <MemoryRouter>
      <AdminContext i18nProvider={polyglotI18nProvider(() => en, 'en')} queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })} dataProvider={testDataProvider({ getList })}>
        <ResourceContextProvider value='WebMapService'>
          <SelectedRecordContextProvider>
            <Selection />
            <HistoryList variant="compact" resource='HistoricalWebMapService' related='WebMapService' />
          </SelectedRecordContextProvider>
        </ResourceContextProvider>
      </AdminContext>
    </MemoryRouter>,
  )
  return { ...result, getList }
}

describe('HistoryList compact variant', () => {
  it('shows compact summaries and queries the latest ten delta events', async () => {
    const { container, getList } = renderHistory()
    expect(await screen.findByText(/Title and 2 other fields changed/)).toBeInTheDocument()
    expect(screen.getByText(/Active changed/)).toBeInTheDocument()
    expect(screen.getByText(/Deleted · Title changed/)).toBeInTheDocument()
    expect(container).not.toHaveTextContent('Old abstract')
    expect(container).not.toHaveTextContent('undefined')
    expect(getList).toHaveBeenCalledWith('HistoricalWebMapService', expect.objectContaining({
      filter: { delta_size__gt: 0 },
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
      meta: { jsonApiParams: { include: 'historyUser', 'fields[User]': 'username,string_representation' } },
    }))
  })

  it('opens full previous and new values in a dialog without hover', async () => {
    renderHistory()
    fireEvent.click(await screen.findByRole('button', { name: /Title and 2 other fields changed/ }))
    const details = within(screen.getByRole('dialog')).getByRole('region', { name: 'Selected event details' })
    expect(details).toHaveTextContent('by alice')
    expect(within(details).getByText('3 changes')).toBeInTheDocument()
    expect(within(details).getAllByText('Previous value')).toHaveLength(3)
    expect(within(details).getByText('Old abstract')).toBeInTheDocument()
    expect(within(details).getByText('https://new.example.com')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('presents geometry, relations and missing values meaningfully', async () => {
    renderHistory(vi.fn().mockResolvedValue({
      data: [{ id: 'geom', title: 'Weather service', historyType: 'updated', historyDate: '2026-10-07T10:00:00Z', historyUser: null, delta: [
        { field: 'the_geom', old: { type: 'Point', coordinates: [1, 2] }, new: { type: 'Point', coordinates: [3, 4] } },
        { field: 'service_contact', old: { _type: 'MetadataContact', id: 'c-1' }, new: null },
      ] }],
      total: 1,
    }))
    fireEvent.click(await screen.findByRole('button', { name: /The Geom and 1 other field changed/ }))
    const details = within(screen.getByRole('dialog')).getByRole('region', { name: 'Selected event details' })
    expect(within(details).getAllByText('Geometry (Point)')).toHaveLength(2)
    expect(within(details).getByText('MetadataContact · c-1')).toBeInTheDocument()
    expect(within(details).getByText('—')).toBeInTheDocument()
  })

  it('links to the full changelog, scoped to the selected service', async () => {
    const { getByRole } = renderHistory()
    await screen.findByText(/Active changed/)
    expect(getByRole('link', { name: 'View all history' })).toHaveAttribute('href', '/WebMapService/history')
    fireEvent.click(screen.getByRole('button', { name: 'Select service' }))
    await waitFor(() => expect(getByRole('link', { name: 'View all history' })).toHaveAttribute(
      'href', `/WebMapService/history?filter=${encodeURIComponent(JSON.stringify({ historyRelation: 'service' }))}`,
    ))
  })

  it('covers empty and error states', async () => {
    const { unmount } = renderHistory(vi.fn().mockResolvedValue({ data: [], total: 0 }))
    expect(await screen.findByText('No changes recorded.')).toBeInTheDocument()
    unmount()
    renderHistory(vi.fn().mockRejectedValue(new Error('Offline')))
    expect(await screen.findByText('Unable to load history.')).toBeInTheDocument()
  })
})

const layerEvents = [{ id: 1, historyType: 'updated', historyDate: '2026-09-18T11:46:40Z', historyRelation: { id: 'layer-id' }, delta: [{ field: 'title', old: 'Old title', new: 'New title' }] }]
const serviceEvents = [{ id: 1, historyType: 'created', historyDate: '2026-08-14T13:24:02Z', historyRelation: { id: 'service-id' } }]

const renderTimeline = (id: string, getList?: (resource: string) => Promise<{ data: unknown[], total: number }>) => render(
  <MemoryRouter>
    <AdminContext
      i18nProvider={polyglotI18nProvider(() => en, 'en')}
      queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      dataProvider={testDataProvider({ getList: (getList ?? ((resource: string) => Promise.resolve({
        data: resource === 'HistoricalLayer' ? layerEvents : serviceEvents,
        total: 1,
      }))) as never })}
    >
      <HistoryList
        variant="timeline"
        record={{ id }}
        sources={[
          historicalSource('HistoricalWebMapService', 'WebMapService', 'Service changes', id, 'historyRelation'),
          historicalSource('HistoricalLayer', 'Layer', 'Layer changes', id, 'service'),
        ]}
      />
    </AdminContext>
  </MemoryRouter>,
)

describe('HistoryList timeline variant', () => {
  it('orders events newest first and clears selection when changing resource filters', async () => {
    renderTimeline('service-id')
    const eventButtons = await screen.findAllByRole('button', { name: /^(Layer|WebMapService) / })
    expect(eventButtons[0]).toHaveAccessibleName(/^Layer/)
    fireEvent.click(eventButtons[0])
    expect(screen.getByText('New title')).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Filter history by resource' }))
    fireEvent.click(screen.getByRole('option', { name: 'Service changes (1)' }))
    await waitFor(() => {
      expect(screen.queryByText('New title')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^Layer / })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^WebMapService / })).toBeInTheDocument()
    })
  })

  it('clears the selected details when navigating to a different service', async () => {
    const { rerender } = renderTimeline('service-id')
    fireEvent.click(await screen.findByRole('button', { name: /^Layer / }))
    expect(await screen.findByRole('region', { name: 'Selected event details' })).toBeInTheDocument()
    rerender(
      <MemoryRouter>
        <AdminContext
          i18nProvider={polyglotI18nProvider(() => en, 'en')}
          queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
          dataProvider={testDataProvider({ getList: vi.fn().mockImplementation(resource => Promise.resolve({
            data: resource === 'HistoricalLayer' ? layerEvents : serviceEvents,
            total: 1,
          })) })}
        >
          <HistoryList
            variant="timeline"
            record={{ id: 'another-service' }}
            sources={[
              historicalSource('HistoricalWebMapService', 'WebMapService', 'Service changes', 'another-service', 'historyRelation'),
              historicalSource('HistoricalLayer', 'Layer', 'Layer changes', 'another-service', 'service'),
            ]}
          />
        </AdminContext>
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Selected event details' })).not.toBeInTheDocument())
  })

  it('shows fetch errors instead of claiming history is empty', async () => {
    renderTimeline('service-id', vi.fn().mockRejectedValue(new Error('Offline')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load history.')
  })
})


