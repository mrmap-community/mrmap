import { act } from 'react'
import { AdminContext, localStorageStore } from 'react-admin'

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Drawer from './Drawer'
import { DrawerBase, useDrawerContext, type DrawerState } from './DrawerContext'

const uiState = vi.hoisted(() => ({ sidebarOpen: true, appBarHeight: 0 }))

const observers = vi.hoisted(() => ({ instances: [] as FakeResizeObserver[] }))

class FakeResizeObserver {
  disconnected = false
  private readonly callback: () => void
  constructor(callback: () => void) {
    this.callback = callback
    observers.instances.push(this)
  }
  observe() { }
  unobserve() { }
  disconnect() {
    this.disconnected = true
  }
  trigger() {
    act(this.callback)
  }
}

vi.mock('react-admin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-admin')>()),
  useSidebarState: () => [uiState.sidebarOpen, vi.fn()],
}))

vi.stubGlobal('ResizeObserver', FakeResizeObserver)

const RIGHT: DrawerState = { isOpen: false, height: 'calc(100vh - 50px)', width: '20vw' }
const BOTTOM: DrawerState = { isOpen: false, height: '30vh', width: '100vw' }

// react-admin's localStorageStore prefixes every key with "RaStore."
const setStored = (key: string, value: unknown) => {
  localStorage.setItem(`RaStore.mrmap.drawer.${key}`, JSON.stringify(value))
}

const storedOpen = (key: string) => {
  const stored = localStorage.getItem(`RaStore.mrmap.drawer.${key}`)
  return stored !== null && JSON.parse(stored).isOpen === true
}

const viewer = (callback: () => void = () => { }) => (
  <AdminContext store={localStorageStore()}>
    <DrawerBase>
      <header role="banner" />
      <div id="viewer-target" />
      <Drawer anchor="right" instanceKey="rightdrawer" defaults={RIGHT} targetId="viewer-target" callback={callback}>
        right content
      </Drawer>
      <Drawer anchor="bottom" instanceKey="bottomdrawer" defaults={BOTTOM} targetId="viewer-target" callback={callback}>
        bottom content
      </Drawer>
    </DrawerBase>
  </AdminContext>
)

const paperOf = (container: HTMLElement, anchor: 'Right' | 'Bottom') =>
  container.querySelector<HTMLElement>(`.MuiDrawer-anchor${anchor} .MuiDrawer-paper`)!

const target = () => document.getElementById('viewer-target')!

const extentsOf = (container: HTMLElement) => ({
  rightWidth: paperOf(container, 'Right').style.width,
  rightHeight: paperOf(container, 'Right').style.height,
  bottomWidth: paperOf(container, 'Bottom').style.width,
  bottomHeight: paperOf(container, 'Bottom').style.height,
})

const openRight = () => fireEvent.click(screen.getByRole('button', { name: 'drawer.openRight' }))
const closeRight = () => fireEvent.click(screen.getByRole('button', { name: 'drawer.closeRight' }))
const openBottom = () => fireEvent.click(screen.getByRole('button', { name: 'drawer.openBottom' }))
const closeBottom = () => fireEvent.click(screen.getByRole('button', { name: 'drawer.closeBottom' }))

beforeEach(() => {
  localStorage.clear()
  uiState.sidebarOpen = true
  uiState.appBarHeight = 0
  observers.instances.length = 0
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const height = this.getAttribute?.('role') === 'banner' ? uiState.appBarHeight : 0
    return { bottom: height, height, left: 0, right: 0, top: 0, width: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('placement and toggles', () => {
  it('renders both anchors closed with accessible toggle buttons', () => {
    const { container } = render(viewer())
    expect(paperOf(container, 'Right')).toBeInTheDocument()
    expect(paperOf(container, 'Bottom')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'drawer.openRight' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'drawer.openBottom' })).toBeInTheDocument()
    expect(paperOf(container, 'Right').style.width).toBe('20vw')
    expect(paperOf(container, 'Bottom').style.height).toBe('30vh')
    expect(paperOf(container, 'Bottom').style.marginLeft).toBe('250px')
    expect(target().style.paddingRight).toBe('0px')
    expect(target().style.paddingBottom).toBe('0px')
  })

  it('names the buttons after the state and lets them be focused', () => {
    render(viewer())
    const button = screen.getByRole('button', { name: 'drawer.openRight' })
    button.focus()
    expect(button).toHaveFocus()
    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'drawer.closeRight' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'drawer.openRight' })).toBeNull()
  })
})

describe('reciprocal sizing', () => {
  it('shrinks the right drawer in height and the bottom drawer in width when both are open', () => {
    const { container } = render(viewer())
    openRight()
    openBottom()
    const right = paperOf(container, 'Right')
    const bottom = paperOf(container, 'Bottom')
    expect(right.style.width).toBe('20vw')
    expect(right.style.height).toContain('30vh')
    expect(bottom.style.height).toBe('30vh')
    expect(bottom.style.width).toContain('20vw')
    expect(target().style.paddingRight).toBe('20vw')
    expect(target().style.paddingBottom).toBe('30vh')
  })

  it('leaves the orthogonal extent untouched when only one drawer is open', () => {
    const { container } = render(viewer())
    openRight()
    expect(paperOf(container, 'Right').style.height).not.toContain('30vh')
    expect(paperOf(container, 'Right').style.width).toBe('20vw')
    closeRight()
    openBottom()
    expect(paperOf(container, 'Bottom').style.height).toBe('30vh')
    expect(paperOf(container, 'Bottom').style.width).not.toContain('20vw')
  })

  it('restores the same layout for either opening order and after repeated toggles', () => {
    const { container } = render(viewer())
    openRight()
    openBottom()
    const firstRound = extentsOf(container)
    closeRight()
    closeBottom()
    expect(extentsOf(container)).not.toMatchObject({
      rightHeight: firstRound.rightHeight,
      bottomWidth: firstRound.bottomWidth,
    })
    openBottom()
    openRight()
    expect(extentsOf(container)).toEqual(firstRound)
    closeBottom()
    closeRight()
    openRight()
    openBottom()
    expect(extentsOf(container)).toEqual(firstRound)
  })

  it('closes into the configured dimensions of the other drawer, not its constrained ones', () => {
    const { container } = render(viewer())
    openBottom()
    openRight()
    expect(paperOf(container, 'Bottom').style.width).toContain('20vw')
    closeRight()
    expect(paperOf(container, 'Bottom').style.width).not.toContain('20vw')
    expect(target().style.paddingRight).toBe('0px')
    expect(target().style.paddingBottom).toBe('30vh')
  })

  it('derives the constraints from configured dimensions read from the store', () => {
    setStored('rightdrawer', { isOpen: true, height: '100%', width: '12vw' })
    setStored('bottomdrawer', { isOpen: true, height: '44vh', width: '100vw' })
    const { container } = render(viewer())
    expect(paperOf(container, 'Right').style.height).toContain('44vh')
    expect(paperOf(container, 'Bottom').style.width).toContain('12vw')
    expect(target().style.paddingRight).toBe('12vw')
  })
})

describe('layout state', () => {
  it('re-measures the app bar and keeps the drawer in sync', () => {
    const { container } = render(viewer())
    openRight()
    expect(paperOf(container, 'Right').style.paddingTop).toBe('0px')
    uiState.appBarHeight = 64
    observers.instances[0].trigger()
    expect(paperOf(container, 'Right').style.paddingTop).toBe('64px')
    expect(paperOf(container, 'Right').style.height).toContain('64px')
    expect(target().style.paddingRight).toBe('20vw')
  })

  it('follows the sidebar state for the bottom drawer', () => {
    const { container, rerender } = render(viewer())
    openBottom()
    expect(paperOf(container, 'Bottom').style.marginLeft).toBe('250px')
    expect(paperOf(container, 'Bottom').style.width).toContain('250px')
    uiState.sidebarOpen = false
    rerender(viewer())
    expect(paperOf(container, 'Bottom').style.marginLeft).toBe('58px')
    expect(paperOf(container, 'Bottom').style.width).toContain('58px')
  })

  it('disconnects the observer and resets the padding on unmount', () => {
    const { container, unmount } = render(viewer())
    openRight()
    const element = target()
    expect(element.style.paddingRight).toBe('20vw')
    unmount()
    expect(element.style.paddingRight).toBe('0px')
    expect(observers.instances[0].disconnected).toBe(true)
    expect(container).toBeEmptyDOMElement()
  })

  it('runs the callback on every toggle', () => {
    const callback = vi.fn()
    render(viewer(callback))
    const callsAfterMount = callback.mock.calls.length
    openRight()
    expect(callback.mock.calls.length).toBeGreaterThan(callsAfterMount)
    const callsAfterToggle = callback.mock.calls.length
    openBottom()
    expect(callback.mock.calls.length).toBeGreaterThan(callsAfterToggle)
  })

  it('opens a drawer by its instance key from the layout context', () => {
    const OpenBottomButton = () => {
      const { openDrawer } = useDrawerContext()
      return <button onClick={() => openDrawer('bottomdrawer')}>open-bottom</button>
    }
    render(
      <AdminContext store={localStorageStore()}>
        <DrawerBase>
          <div id="viewer-target" />
          <Drawer anchor="bottom" instanceKey="bottomdrawer" defaults={BOTTOM} targetId="viewer-target">
            bottom content
          </Drawer>
          <OpenBottomButton />
        </DrawerBase>
      </AdminContext>
    )
    fireEvent.click(screen.getByRole('button', { name: 'open-bottom' }))
    expect(screen.getByRole('button', { name: 'drawer.closeBottom' })).toBeInTheDocument()
    expect(target().style.paddingBottom).toBe('30vh')
  })
})

describe('instance state', () => {
  it('persists toggles under the instance store key only', async () => {
    render(viewer())
    openRight()
    await waitFor(() => expect(storedOpen('rightdrawer')).toBe(true))
    expect(storedOpen('bottomdrawer')).toBe(false)
  })

  it('reads a previously persisted state including its legacy fields', () => {
    setStored('rightdrawer', { isOpen: true, height: '100%', width: '300px', marginLeft: '58px', children: null })
    const { container } = render(viewer())
    expect(paperOf(container, 'Right').style.width).toBe('300px')
    expect(screen.getByRole('button', { name: 'drawer.closeRight' })).toBeInTheDocument()
    expect(target().style.paddingRight).toBe('300px')
  })

  it('keeps two instances of the same anchor independent', () => {
    const FIRST: DrawerState = { isOpen: false, height: '10%', width: '11vw' }
    const SECOND: DrawerState = { isOpen: false, height: '10%', width: '12vw' }
    render(
      <AdminContext store={localStorageStore()}>
        <DrawerBase>
          <div data-testid="first">
            <Drawer anchor="right" instanceKey="first" defaults={FIRST}>first</Drawer>
          </div>
          <div data-testid="second">
            <Drawer anchor="right" instanceKey="second" defaults={SECOND}>second</Drawer>
          </div>
        </DrawerBase>
      </AdminContext>
    )
    const firstElement = screen.getByTestId('first')
    const secondElement = screen.getByTestId('second')
    const first = within(firstElement)
    const second = within(secondElement)
    fireEvent.click(first.getByRole('button'))
    expect(first.getByRole('button')).toHaveAccessibleName('drawer.closeRight')
    expect(second.getByRole('button')).toHaveAccessibleName('drawer.openRight')
    expect(firstElement.querySelector<HTMLElement>('.MuiDrawer-paper')!.style.width).toBe('11vw')
    expect(secondElement.querySelector<HTMLElement>('.MuiDrawer-paper')!.style.width).toBe('12vw')
    // same-anchor instances do not constrain each other
    expect(firstElement.querySelector<HTMLElement>('.MuiDrawer-paper')!.style.height).not.toContain('12vw')
    expect(storedOpen('first')).toBe(true)
    expect(storedOpen('second')).toBe(false)
  })
})
