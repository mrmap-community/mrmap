import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AdminContext, ResourceContextProvider, testDataProvider } from 'react-admin'
import { describe, expect, it, vi } from 'vitest'
import polyglotI18nProvider from 'ra-i18n-polyglot'
import en from '../i18n/en'
import { SelectedRecordContextProvider, useSelectedRecordContext } from '../jsonapi/components/SelectedRecordContext'
import HistoryList from './HistoryList'

const events = [
  { id: 'one', title: 'Weather service', historyType: 'updated', historyDate: '2026-10-07T12:15:00Z', delta: [], historyUser: null },
  { id: 'two', title: 'Weather service', historyType: 'created', historyDate: '2026-10-07T12:00:00Z', historyUser: { username: 'alice' } },
  { id: 'three', title: 'Weather service', historyType: 'deleted', historyDate: '2026-10-07T11:00:00Z', delta: [{ field: 'title', old: 'Old title', new: 'New title' }] },
]

const Selection = () => {
  const { setSelectedRecord } = useSelectedRecordContext()
  return <button onClick={() => setSelectedRecord({ id: 'service', title: 'Weather service' })}>Select service</button>
}

const renderHistory = () => {
  const getList = vi.fn().mockResolvedValue({ data: events, total: events.length })
  const result = render(
    <AdminContext i18nProvider={polyglotI18nProvider(() => en, 'en')} dataProvider={testDataProvider({ getList })}>
      <ResourceContextProvider value='WebMapService'>
        <SelectedRecordContextProvider>
          <Selection />
          <HistoryList resource='HistoricalWebMapService' related='WebMapService' record={undefined} />
        </SelectedRecordContextProvider>
      </ResourceContextProvider>
    </AdminContext>
  )
  return { ...result, getList }
}

describe('HistoryList', () => {
  it('shows event labels, dates and recorded authors without missing-user text', async () => {
    const { container } = renderHistory()
    expect(await screen.findByText('Weather service · Updated')).toBeInTheDocument()
    expect(screen.getByText('Weather service · Created')).toBeInTheDocument()
    expect(screen.getByText('Weather service · Deleted')).toBeInTheDocument()
    expect(screen.getByText(/alice/)).toBeInTheDocument()
    expect(container).not.toHaveTextContent('undefined')
    expect(container.querySelector('.MuiChip-root')).toBeNull()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('updates row content and scopes the latest ten events when selection changes', async () => {
    const { getList } = renderHistory()
    await screen.findByText('Weather service · Updated')
    fireEvent.click(screen.getByRole('button', { name: 'Select service' }))
    expect(await screen.findByText('Updated')).toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText('Deleted · title')).toBeInTheDocument()
    await waitFor(() => expect(getList).toHaveBeenLastCalledWith('HistoricalWebMapService', expect.objectContaining({
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
      meta: { jsonApiParams: expect.objectContaining({ 'filter[historyRelation]': 'service' }) },
    })))
  })

  it('keeps the full changed values available in a tooltip', async () => {
    renderHistory()
    const event = await screen.findByText('Weather service · Deleted')
    fireEvent.mouseOver(event)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('title: Old title → New title')
  })
})
