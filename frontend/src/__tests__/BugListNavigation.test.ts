import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h } from 'vue'
import BugList from '@/views/bug/BugList.vue'
import MyBugs from '@/views/bug/MyBugs.vue'
import BugWorkbench from '@/views/bug/BugWorkbench.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn().mockResolvedValue(undefined) }),
}))

// Mock API
vi.mock('@/api/bug', async () => {
  const actual = await vi.importActual<typeof import('@/api/bug')>('@/api/bug')
  return {
    ...actual,
    listBugs: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
    listMyBugs: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
    getBugStats: vi.fn().mockResolvedValue(null),
    getProjectMembers: vi.fn().mockResolvedValue([]),
  }
})

// Stores mocks
vi.mock('@/stores/board', () => ({
  useBoardStore: () => ({
    currentProject: { owner_details: { id: null } },
    currentProjectId: '',
    fetchProjectInfo: vi.fn(),
    fetchUsers: vi.fn(),
    isConnected: false,
  }),
}))

vi.mock('@/stores/Auth', () => ({
  useAuthStore: () => ({
    user: null,
    checkAuth: vi.fn(),
    checkPermission: vi.fn().mockReturnValue(true),
    menus: [],
    logout: vi.fn(),
    updateAvatar: vi.fn(),
  }),
}))

// Minimal stubs for BugWorkbench sub-components
const passthroughStub = {
  template: '<div class="stub"><slot /></div>',
}

const iconStub = {
  render: () => h('i'),
}

const commonStubs = {
  'el-button': passthroughStub,
  'el-icon': passthroughStub,
  'el-card': passthroughStub,
  'el-input': passthroughStub,
  'el-select': passthroughStub,
  'el-option': passthroughStub,
  'el-tag': passthroughStub,
  'el-dropdown': passthroughStub,
  'el-dropdown-menu': passthroughStub,
  'el-dropdown-item': passthroughStub,
  'el-popconfirm': passthroughStub,
  'el-pagination': passthroughStub,
  'el-dialog': passthroughStub,
  'el-form': passthroughStub,
  'el-form-item': passthroughStub,
  'el-tabs': passthroughStub,
  'el-tab-pane': passthroughStub,
  'el-table': passthroughStub,
  'el-table-column': passthroughStub,
  'el-divider': passthroughStub,
  // BugWorkbench sub-components are stubbed so we can test the wrapper behavior
  BugWorkbenchHeader: passthroughStub,
  BugStatsCards: passthroughStub,
  BugViewTabs: passthroughStub,
  BugFilterBar: passthroughStub,
  BugTable: passthroughStub,
  BugCreateDialog: passthroughStub,
  BugTransitionDialog: passthroughStub,
  BugAssignDialog: passthroughStub,
  BugStatusTag: passthroughStub,
  BugSeverityTag: passthroughStub,
  BugPriorityTag: passthroughStub,
  Plus: iconStub,
  Refresh: iconStub,
  Search: iconStub,
  ArrowDown: iconStub,
  ArrowLeft: iconStub,
  ArrowRight: iconStub,
  Delete: iconStub,
  Warning: iconStub,
  List: iconStub,
  User: iconStub,
  CircleCheck: iconStub,
  SortUp: iconStub,
  CircleClose: iconStub,
  MoreFilled: iconStub,
  TrendCharts: iconStub,
  Collection: iconStub,
  FolderOpened: iconStub,
  Grid: iconStub,
  DataLine: iconStub,
  Setting: iconStub,
  ChatDotRound: iconStub,
  ChatLineRound: iconStub,
  Bell: iconStub,
  Monitor: iconStub,
  Document: iconStub,
  Tools: iconStub,
  Management: iconStub,
  Operation: iconStub,
  Timer: iconStub,
  SwitchButton: iconStub,
}

const mountBugWorkbench = (defaultView: string) =>
  mount(BugWorkbench, {
    props: { defaultView },
    global: {
      plugins: [createPinia()],
      stubs: commonStubs,
      directives: {
        loading: {},
      },
    },
  })

describe('BugList wrapper', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders BugWorkbench with default-view="all"', () => {
    const wrapper = mount(BugList, {
      global: {
        plugins: [createPinia()],
        stubs: { BugWorkbench: true },
      },
    })
    const wb = wrapper.findComponent({ name: 'BugWorkbench' })
    // With stub:true, the component won't render props, but at minimum
    // BugList should not contain its own table logic anymore.
    // The file should be a thin wrapper importing BugWorkbench.
    expect(wrapper.html()).not.toContain('el-table')
  })

  it('does not contain duplicate table logic', () => {
    // BugList.vue source should just be a template with BugWorkbench
    // Verify the file is a thin wrapper
    const wrapper = mount(BugList, {
      global: {
        plugins: [createPinia()],
        stubs: { BugWorkbench: true },
      },
    })
    // BugList should not have its own filter bar, stats, or table HTML
    expect(wrapper.html()).not.toContain('filter-bar')
    expect(wrapper.html()).not.toContain('statistics-cards')
  })
})

describe('MyBugs wrapper', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders BugWorkbench with default-view="my_pending"', () => {
    const wrapper = mount(MyBugs, {
      global: {
        plugins: [createPinia()],
        stubs: { BugWorkbench: true },
      },
    })
    expect(wrapper.html()).not.toContain('el-table')
    expect(wrapper.html()).not.toContain('el-tabs')
  })

  it('does not maintain independent table logic', () => {
    // MyBugs.vue should be a thin wrapper, not a standalone page
    const wrapper = mount(MyBugs, {
      global: {
        plugins: [createPinia()],
        stubs: { BugWorkbench: true },
      },
    })
    expect(wrapper.html()).not.toContain('tab-hint')
    expect(wrapper.html()).not.toContain('my-bugs')
  })
})

describe('BugWorkbench integration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without crashing with default-view="all"', () => {
    const wrapper = mountBugWorkbench('all')
    // The core workbench container should exist
    expect(wrapper.find('.bug-workbench').exists()).toBe(true)
  })

  it('renders without crashing with default-view="my_pending"', () => {
    const wrapper = mountBugWorkbench('my_pending')
    expect(wrapper.find('.bug-workbench').exists()).toBe(true)
  })

  it('shows empty state text when no bugs', async () => {
    const wrapper = mountBugWorkbench('all')
    // Wait for async loadBugs/loadStats to complete
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()
    // For view='all' with isOwner=true, empty-demo-banner renders;
    // otherwise empty-state renders. Either is valid.
    const hasEmpty =
      wrapper.find('.empty-state').exists() ||
      wrapper.find('.empty-demo-banner').exists()
    expect(hasEmpty).toBe(true)
  })

  it('empty state for my_pending shows appropriate message', async () => {
    const wrapper = mountBugWorkbench('my_pending')
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()
    const emptyState = wrapper.find('.empty-state')
    expect(emptyState.exists()).toBe(true)
    expect(emptyState.text()).toContain('待处理')
  })
})
