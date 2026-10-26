import { AdminContext, ResourceContextProvider, ResourceDefinitionContextProvider, testDataProvider } from 'react-admin'
import { MemoryRouter } from 'react-router-dom'

import { QueryClient } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import polyglotI18nProvider from 'ra-i18n-polyglot'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import en from '../../../i18n/en'
import ChangeLogList from './ChangeLogList'

const getOperation = vi.hoisted(() => vi.fn())

vi.mock('../../../context/HttpClientContext', () => ({
  useHttpClientContext: () => ({ api: { getOperation } }),
}))

const renderCard = () => {
  const getList = vi.fn().mockResolvedValue({
    data: [{
      id: 'change',
      title: 'Weather service',
      historyType: 'updated',
      historyDate: '2026-10-07T12:15:00Z',
      historyUser: { username: 'alice' },
      delta: [{ field: 'title', old: 'Old title', new: 'New title' }],
    }],
    total: 1,
  })
  render(
    <MemoryRouter>
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, 'en')}
        queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        dataProvider={testDataProvider({ getList })}
      >
        <ResourceDefinitionContextProvider definitions={{ WebMapService: { name: 'WebMapService' } }}>
          <ResourceContextProvider value='WebMapService'>
            <ChangeLogList />
          </ResourceContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </MemoryRouter>,
  )
  return getList
}

beforeEach(() => {
  getOperation.mockReset().mockReturnValue({})
})

describe('ChangeLogList', () => {
  it('loads a compact feed on expansion and opens full details from an event', async () => {
    const getList = renderCard()
    expect(getList).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Last Changes' }))
    const event = await screen.findByRole('button', { name: /Weather service · Title changed/ })
    expect(event).toHaveTextContent('alice')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/Rows per page/)).not.toBeInTheDocument()
    expect(getList).toHaveBeenCalledWith('HistoricalWebMapService', expect.objectContaining({
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
    }))
    expect(screen.getByRole('link', { name: 'View all history' })).toHaveAttribute('href', '/WebMapService/history')
    fireEvent.click(event)
    expect(within(screen.getByRole('dialog')).getByText('Old title')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByText('New title')).toBeInTheDocument()
  })

  it('hides history for resources without a historical endpoint', () => {
    getOperation.mockReturnValue(undefined)
    const getList = renderCard()
    expect(screen.queryByRole('button', { name: 'Last Changes' })).not.toBeInTheDocument()
    expect(getList).not.toHaveBeenCalled()
  })
})
