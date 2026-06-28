import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import QA from '@/views/QA.vue'
import TestConsole from '@/components/TestConsole.vue'
import service from '@/utils/request'

vi.mock('@/utils/request', () => ({
  default: {
    post: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-42' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

const fetchColumns = vi.fn()
vi.mock('@/stores/board', () => ({
  useBoardStore: () => ({
    Columns: [],
    currentProject: { id: 'project-42' },
    fetchColumns,
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

const passthroughStub = {
  template: '<div><slot /><slot name="header" /><slot name="footer" /><slot name="dropdown" /></div>',
}

const iconStub = {
  template: '<i><slot /></i>',
}

class MockWebSocket {
  static OPEN = 1
  static createdUrls: string[] = []
  readyState = MockWebSocket.OPEN
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(url: string) {
    MockWebSocket.createdUrls.push(url)
  }

  close() {}
}

const globalMountOptions = {
  stubs: {
    'el-card': passthroughStub,
    'el-button': passthroughStub,
    'el-icon': passthroughStub,
    'el-progress': passthroughStub,
    'el-dialog': passthroughStub,
    'el-form': passthroughStub,
    'el-form-item': passthroughStub,
    'el-select': passthroughStub,
    'el-option': passthroughStub,
    'el-input-number': passthroughStub,
    'el-checkbox': passthroughStub,
    'el-dropdown': passthroughStub,
    'el-dropdown-menu': passthroughStub,
    'el-dropdown-item': passthroughStub,
    'el-alert': passthroughStub,
    'el-tag': passthroughStub,
    Loading: iconStub,
    VideoPlay: iconStub,
    Delete: iconStub,
    MagicStick: iconStub,
    Connection: iconStub,
    Monitor: iconStub,
    Odometer: iconStub,
    DataAnalysis: iconStub,
  },
}

describe('QA quick test project-scoped websocket', () => {
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
    vi.mocked(service.post).mockResolvedValue({ msg: 'ok' })
  })

  it('QA page connects and starts quick tests with the current project id', async () => {
    const wrapper = mount(QA, { global: globalMountOptions })

    await (wrapper.vm as any).startTest('api')

    expect(MockWebSocket.createdUrls).toContain(
      'ws://localhost:8000/ws/qa/dashboard/project-42/',
    )
    expect(service.post).toHaveBeenCalledWith('/qa/run-test/', {
      test_type: 'api',
      project_id: 'project-42',
    })
  })

  it('TestConsole uses project scope when projectId prop is provided', async () => {
    const wrapper = mount(TestConsole, {
      props: { projectId: 'project-99' },
      global: globalMountOptions,
    })

    ;(wrapper.vm as any).open()
    await (wrapper.vm as any).startTest('regression')

    expect(MockWebSocket.createdUrls).toEqual([
      'ws://localhost:8000/ws/qa/dashboard/project-99/',
    ])
    expect(service.post).toHaveBeenCalledWith('/qa/run-test/', {
      test_type: 'regression',
      project_id: 'project-99',
    })
  })
})
