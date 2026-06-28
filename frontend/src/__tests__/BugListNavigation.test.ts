import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h } from 'vue'
import BugList from '@/views/bug/BugList.vue'
import MyBugs from '@/views/bug/MyBugs.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/api/bug', async () => {
  const actual = await vi.importActual<typeof import('@/api/bug')>('@/api/bug')
  return {
    ...actual,
    listBugs: vi.fn().mockResolvedValue({ count: 0, results: [] }),
    listMyBugs: vi.fn().mockResolvedValue({ count: 0, results: [] }),
    getBugStats: vi.fn().mockResolvedValue(null),
    getProjectMembers: vi.fn().mockResolvedValue([]),
  }
})

const tableStub = {
  name: 'ElTable',
  props: ['data', 'rowClassName'],
  template: '<div class="el-table"><slot /></div>',
}

const tableColumnStub = {
  name: 'ElTableColumn',
  props: ['prop', 'label'],
  template: '<div class="el-table-column"><slot :row="{ id: 1, title: \'示例 Bug\' }" /></div>',
}

const passthroughStub = {
  template: '<div><slot /></div>',
}

const iconStub = {
  render: () => h('i'),
}

const commonStubs = {
  'el-table': tableStub,
  'el-table-column': tableColumnStub,
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
  TrendCharts: iconStub,
  Refresh: iconStub,
  Plus: iconStub,
  Search: iconStub,
  ArrowDown: iconStub,
  Delete: iconStub,
}

const mountPage = (component: typeof BugList | typeof MyBugs) => mount(component, {
  global: {
    plugins: [createPinia()],
    stubs: commonStubs,
    directives: {
      loading: {},
    },
  },
})

describe('Bug list navigation affordance', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not render Bug 管理 table as a clickable row table and provides a title link', () => {
    const wrapper = mountPage(BugList)

    const table = wrapper.findComponent(tableStub)

    expect((table.vm as any).$attrs.onRowClick).toBeUndefined()
    expect(table.props('rowClassName')).toBeUndefined()
    expect(wrapper.find('.bug-title-link').exists()).toBe(true)
  })

  it('does not render 我的 Bug table as a clickable row table and provides a title link', () => {
    const wrapper = mountPage(MyBugs)

    const table = wrapper.findComponent(tableStub)

    expect((table.vm as any).$attrs.onRowClick).toBeUndefined()
    expect(table.props('rowClassName')).toBeUndefined()
    expect(wrapper.find('.bug-title-link').exists()).toBe(true)
  })
})
