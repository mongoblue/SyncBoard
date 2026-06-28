import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import BatchRunExecuteDialog from '@/views/qa/components/BatchRunExecuteDialog.vue'
import { createRunPlan, executeRunPlan } from '@/api/runplan'

vi.mock('@/api/runplan', () => ({
  listSelectableCases: vi.fn().mockResolvedValue({ count: 1, results: [] }),
  createRunPlan: vi.fn(),
  executeRunPlan: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
  },
}))

const passthroughStub = {
  template: '<div><slot /><slot name="footer" /></div>',
}

const tableColumnStub = {
  props: ['type', 'prop', 'label'],
  template: '<div><slot :row="{ id: 101, method: \'GET\', name: \'登录用例\', url: \'/login\', suite_name: \'核心\' }" /></div>',
}

const iconStub = {
  template: '<i><slot /></i>',
}

class MockWebSocket {
  static createdUrls: string[] = []

  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    MockWebSocket.createdUrls.push(url)
  }

  close() {
    this.onclose?.()
  }
}

describe('BatchRunExecuteDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockWebSocket.createdUrls = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        protocol: 'http:',
        hostname: 'localhost',
        host: 'localhost:5173',
      },
    })
    vi.mocked(createRunPlan).mockResolvedValue({ id: 7 } as any)
    vi.mocked(executeRunPlan).mockResolvedValue({ detail: 'ok', plan_id: 7 })
  })

  it('connects run-plan progress WebSocket to the project-scoped dashboard', async () => {
    const wrapper = mount(BatchRunExecuteDialog, {
      props: {
        modelValue: true,
        projectId: 'project-42',
      },
      global: {
        directives: {
          loading: {},
        },
        stubs: {
          'el-dialog': passthroughStub,
          'el-form': passthroughStub,
          'el-form-item': passthroughStub,
          'el-input': passthroughStub,
          'el-switch': passthroughStub,
          'el-input-number': passthroughStub,
          'el-divider': passthroughStub,
          'el-table': passthroughStub,
          'el-table-column': tableColumnStub,
          'el-button': passthroughStub,
          'el-progress': passthroughStub,
          'el-empty': passthroughStub,
          'el-select': passthroughStub,
          'el-option': passthroughStub,
          'el-icon': passthroughStub,
          Search: iconStub,
          Loading: iconStub,
          CircleCheck: iconStub,
          CircleClose: iconStub,
          InfoFilled: iconStub,
          Warning: iconStub,
        },
      },
    })

    ;(wrapper.vm as any).form.name = '登录回归'
    ;(wrapper.vm as any).selectedIds = new Set([101])

    await (wrapper.vm as any).startExecution()
    await nextTick()

    expect(createRunPlan).toHaveBeenCalledWith(expect.objectContaining({ project: 'project-42' }))
    expect(MockWebSocket.createdUrls).toEqual([
      'ws://localhost:8000/ws/qa/dashboard/project-42/',
    ])
  })
})
