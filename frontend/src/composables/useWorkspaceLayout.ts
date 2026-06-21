import { computed, ref, type Ref } from 'vue'

type WorkspaceTabId = 'monitor' | 'report'

type UseWorkspaceLayoutOptions = {
  mainGridRef: Ref<HTMLElement | null>
  desktopBreakpoint?: number
}

export type WorkspaceLayoutState = {
  isDesktopLayout: ReturnType<typeof ref<boolean>>
  isWorkspaceCollapsed: ReturnType<typeof ref<boolean>>
  isResizingWorkspace: ReturnType<typeof ref<boolean>>
  canResizeWorkspace: ReturnType<typeof computed<boolean>>
  canShowWorkspaceCollapseControl: ReturnType<typeof computed<boolean>>
  mainGridStyle: ReturnType<typeof computed<Record<string, string> | null>>
  toggleWorkspaceCollapsed: () => void
  setWorkspaceCollapsed: (collapsed: boolean) => void
  startWorkspaceResize: (event: PointerEvent) => void
  handleWorkspaceResizeKeydown: (event: KeyboardEvent) => void
  resetWorkspaceWidth: () => void
  initializeWorkspaceLayout: () => void
  disposeWorkspaceLayout: () => void
  switchWorkspaceFromRail: (tab: WorkspaceTabId, onSwitch: (tab: WorkspaceTabId) => void) => void
}

const WORKSPACE_WIDTH_STORAGE_KEY = 'demo2opt.workspace-width'
const WORKSPACE_COLLAPSED_STORAGE_KEY = 'demo2opt.workspace-collapsed'
const WORKSPACE_DEFAULT_WIDTH = 560
const WORKSPACE_MIN_WIDTH = 420
const WORKSPACE_MAX_RATIO = 0.72
const WORKSPACE_RESIZE_STEP = 24
const WORKSPACE_RESIZER_WIDTH = 10
const WORKSPACE_RAIL_WIDTH = 56
const LEFT_PANE_SAFE_MIN_WIDTH = 420

export function useWorkspaceLayout({
  mainGridRef,
  desktopBreakpoint = 980,
}: UseWorkspaceLayoutOptions): WorkspaceLayoutState {
  const workspaceWidth = ref(WORKSPACE_DEFAULT_WIDTH)
  const isResizingWorkspace = ref(false)
  const isDesktopLayout = ref(typeof window === 'undefined' ? true : window.innerWidth > desktopBreakpoint)
  const mainGridWidth = ref(0)
  const isWorkspaceCollapsed = ref(false)

  let resizeStartX = 0
  let resizeStartWidth = WORKSPACE_DEFAULT_WIDTH

  const canShowWorkspaceCollapseControl = computed(() => isDesktopLayout.value)
  const canResizeWorkspace = computed(() => {
    if (!isDesktopLayout.value || isWorkspaceCollapsed.value) return false
    return mainGridWidth.value >= WORKSPACE_MIN_WIDTH + LEFT_PANE_SAFE_MIN_WIDTH + WORKSPACE_RESIZER_WIDTH
  })

  const mainGridStyle = computed(() => {
    if (!isDesktopLayout.value) return null
    if (isWorkspaceCollapsed.value) {
      return {
        gridTemplateColumns: `minmax(0, 1fr) ${WORKSPACE_RAIL_WIDTH}px`,
      }
    }
    if (!canResizeWorkspace.value) return null
    return {
      gridTemplateColumns: `minmax(0, 1fr) ${WORKSPACE_RESIZER_WIDTH}px minmax(${WORKSPACE_MIN_WIDTH}px, ${workspaceWidth.value}px)`,
    }
  })

  function updateMainGridMetrics() {
    mainGridWidth.value = mainGridRef.value?.clientWidth || 0
    isDesktopLayout.value = window.innerWidth > desktopBreakpoint
  }

  function getWorkspaceWidthBounds() {
    if (!mainGridWidth.value) return { min: WORKSPACE_MIN_WIDTH, max: WORKSPACE_DEFAULT_WIDTH }
    const maxByRatio = Math.floor(mainGridWidth.value * WORKSPACE_MAX_RATIO)
    const maxByLeftPane = Math.floor(mainGridWidth.value - LEFT_PANE_SAFE_MIN_WIDTH - WORKSPACE_RESIZER_WIDTH)
    const max = Math.max(WORKSPACE_MIN_WIDTH, Math.min(maxByRatio, maxByLeftPane))
    return { min: WORKSPACE_MIN_WIDTH, max }
  }

  function clampWorkspaceWidth(width: number) {
    const { min, max } = getWorkspaceWidthBounds()
    return Math.min(Math.max(width, min), max)
  }

  function saveWorkspaceWidth() {
    try {
      window.localStorage.setItem(WORKSPACE_WIDTH_STORAGE_KEY, String(workspaceWidth.value))
    } catch {
      // ignore localStorage errors
    }
  }

  function saveWorkspaceCollapsed() {
    try {
      window.localStorage.setItem(WORKSPACE_COLLAPSED_STORAGE_KEY, isWorkspaceCollapsed.value ? '1' : '0')
    } catch {
      // ignore localStorage errors
    }
  }

  function applyStoredWorkspaceState() {
    try {
      const storedWidth = Number(window.localStorage.getItem(WORKSPACE_WIDTH_STORAGE_KEY))
      workspaceWidth.value = Number.isFinite(storedWidth) ? clampWorkspaceWidth(storedWidth) : WORKSPACE_DEFAULT_WIDTH
    } catch {
      workspaceWidth.value = WORKSPACE_DEFAULT_WIDTH
    }

    try {
      const storedCollapsed = window.localStorage.getItem(WORKSPACE_COLLAPSED_STORAGE_KEY)
      isWorkspaceCollapsed.value = storedCollapsed === '1'
    } catch {
      isWorkspaceCollapsed.value = false
    }
  }

  function resetWorkspaceWidth() {
    workspaceWidth.value = clampWorkspaceWidth(WORKSPACE_DEFAULT_WIDTH)
    saveWorkspaceWidth()
  }

  function syncWorkspaceWidthToLayout() {
    updateMainGridMetrics()
    if (!isDesktopLayout.value) {
      handleWorkspaceResizeEnd()
      return
    }
    if (!canResizeWorkspace.value) {
      workspaceWidth.value = WORKSPACE_DEFAULT_WIDTH
      return
    }
    workspaceWidth.value = clampWorkspaceWidth(workspaceWidth.value)
  }

  function toggleWorkspaceResizeBodyState(active: boolean) {
    document.body.classList.toggle('workspace-resizing', active)
  }

  function handleWorkspaceResizeMove(event: PointerEvent) {
    if (!isResizingWorkspace.value || isWorkspaceCollapsed.value) return
    const delta = event.clientX - resizeStartX
    workspaceWidth.value = clampWorkspaceWidth(resizeStartWidth - delta)
  }

  function handleWorkspaceResizeEnd() {
    if (!isResizingWorkspace.value) return
    isResizingWorkspace.value = false
    toggleWorkspaceResizeBodyState(false)
    window.removeEventListener('pointermove', handleWorkspaceResizeMove)
    window.removeEventListener('pointerup', handleWorkspaceResizeEnd)
    window.removeEventListener('pointercancel', handleWorkspaceResizeEnd)
    saveWorkspaceWidth()
  }

  function startWorkspaceResize(event: PointerEvent) {
    if (!canResizeWorkspace.value) return
    resizeStartX = event.clientX
    resizeStartWidth = workspaceWidth.value
    isResizingWorkspace.value = true
    toggleWorkspaceResizeBodyState(true)
    window.addEventListener('pointermove', handleWorkspaceResizeMove)
    window.addEventListener('pointerup', handleWorkspaceResizeEnd)
    window.addEventListener('pointercancel', handleWorkspaceResizeEnd)
  }

  function handleWorkspaceResizeKeydown(event: KeyboardEvent) {
    if (!canResizeWorkspace.value) return
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      workspaceWidth.value = clampWorkspaceWidth(workspaceWidth.value - WORKSPACE_RESIZE_STEP)
      saveWorkspaceWidth()
      return
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      workspaceWidth.value = clampWorkspaceWidth(workspaceWidth.value + WORKSPACE_RESIZE_STEP)
      saveWorkspaceWidth()
    }
  }

  function setWorkspaceCollapsed(collapsed: boolean) {
    if (!isDesktopLayout.value) return
    if (collapsed === isWorkspaceCollapsed.value) return
    if (collapsed) handleWorkspaceResizeEnd()
    isWorkspaceCollapsed.value = collapsed
    saveWorkspaceCollapsed()
    syncWorkspaceWidthToLayout()
  }

  function toggleWorkspaceCollapsed() {
    setWorkspaceCollapsed(!isWorkspaceCollapsed.value)
  }

  function initializeWorkspaceLayout() {
    updateMainGridMetrics()
    applyStoredWorkspaceState()
    syncWorkspaceWidthToLayout()
    window.addEventListener('resize', syncWorkspaceWidthToLayout)
  }

  function disposeWorkspaceLayout() {
    handleWorkspaceResizeEnd()
    window.removeEventListener('resize', syncWorkspaceWidthToLayout)
    toggleWorkspaceResizeBodyState(false)
  }

  function switchWorkspaceFromRail(tab: WorkspaceTabId, onSwitch: (tab: WorkspaceTabId) => void) {
    onSwitch(tab)
  }

  return {
    isDesktopLayout,
    isWorkspaceCollapsed,
    isResizingWorkspace,
    canResizeWorkspace,
    canShowWorkspaceCollapseControl,
    mainGridStyle,
    toggleWorkspaceCollapsed,
    setWorkspaceCollapsed,
    startWorkspaceResize,
    handleWorkspaceResizeKeydown,
    resetWorkspaceWidth,
    initializeWorkspaceLayout,
    disposeWorkspaceLayout,
    switchWorkspaceFromRail,
  }
}
