import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useBoardStore } from '@/stores/board'
import { useAuthStore } from '@/stores/Auth'
import {
  listBugs,
  listMyBugs,
  createBug,
  deleteBug,
  transitionBug,
  getBugStats,
  seedDemoBugs,
  getProjectMembers,
  updateBug,
  assignBug,
  type BugListItem,
  type BugStats,
  type BugSeverity,
  type BugPriority,
  type BugStatus,
  type ProjectMemberBrief,
  type BugCreatePayload,
} from '@/api/bug'
import { extractErrorMessage } from '@/utils/error'

export interface BugFilters {
  keyword: string
  status: string[]
  severity: string[]
  priority: string[]
  source_test_type: string
  assignee: number | null
}

export function useBugWorkbench(options: { defaultView: string; projectId: string }) {
  const route = useRoute()
  const router = useRouter()
  const boardStore = useBoardStore()
  const authStore = useAuthStore()

  // ── State ──
  const view = ref(options.defaultView)
  const filters = reactive<BugFilters>({
    keyword: '',
    status: [],
    severity: [],
    priority: [],
    source_test_type: '',
    assignee: null,
  })
  const page = ref(1)
  const pageSize = 20
  const total = ref(0)
  const bugs = ref<BugListItem[]>([])
  const stats = ref<BugStats | null>(null)
  const loading = ref(false)
  const statsLoading = ref(false)
  const projectMembers = ref<ProjectMemberBrief[]>([])

  const isOwner = computed(() =>
    boardStore.currentProject?.owner_details?.id === authStore.user?.id
  )

  // ── URL Sync (read initial state) ──
  const initFromUrl = () => {
    const q = route.query
    if (q.view && typeof q.view === 'string') {
      view.value = q.view
    }
    if (q.keyword && typeof q.keyword === 'string') filters.keyword = q.keyword
    if (q.status && typeof q.status === 'string') filters.status = q.status.split(',').filter(Boolean)
    if (q.severity && typeof q.severity === 'string') filters.severity = q.severity.split(',').filter(Boolean)
    if (q.priority && typeof q.priority === 'string') filters.priority = q.priority.split(',').filter(Boolean)
    if (q.source_test_type && typeof q.source_test_type === 'string') filters.source_test_type = q.source_test_type
    if (q.assignee && typeof q.assignee === 'string') filters.assignee = Number(q.assignee) || null
    if (q.page && typeof q.page === 'string') page.value = Number(q.page) || 1
  }

  // ── URL Sync (write) ──
  const syncUrl = () => {
    const query: Record<string, string> = {}
    if (view.value && view.value !== 'all') query.view = view.value
    if (filters.keyword) query.keyword = filters.keyword
    if (filters.status.length) query.status = filters.status.join(',')
    if (filters.severity.length) query.severity = filters.severity.join(',')
    if (filters.priority.length) query.priority = filters.priority.join(',')
    if (filters.source_test_type) query.source_test_type = filters.source_test_type
    if (filters.assignee) query.assignee = String(filters.assignee)
    if (page.value > 1) query.page = String(page.value)

    router.replace({ query }).catch(() => {
      // NavigationDuplicated is expected when query is the same
    })
  }

  // ── Data Loading ──
  const buildListParams = (): Record<string, any> => {
    const params: Record<string, any> = {
      project: options.projectId,
      page: page.value,
      page_size: pageSize,
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status.length) params.status = filters.status.join(',')
    if (filters.severity.length) params.severity = filters.severity.join(',')
    if (filters.priority.length) params.priority = filters.priority.join(',')
    if (filters.source_test_type) params.source_test_type = filters.source_test_type
    if (filters.assignee) params.assignee = filters.assignee
    return params
  }

  const loadBugs = async () => {
    loading.value = true
    try {
      let res
      switch (view.value) {
        case 'my_pending':
          // Exclude closed/rejected so "my pending" shows only actionable bugs
          res = await listMyBugs('assignee', {
            project: options.projectId,
            page: page.value,
            page_size: pageSize,
            status: 'new,confirmed,assigned,fixing,fixed,verifying,reopened',
          })
          break
        case 'reported_by_me':
          res = await listMyBugs('reporter', {
            project: options.projectId,
            page: page.value,
            page_size: pageSize,
          })
          break
        case 'verifying':
          res = await listBugs({
            ...buildListParams(),
            status: 'verifying',
          })
          break
        case 'high_risk':
          res = await listBugs({
            ...buildListParams(),
            risk: 'high',
          })
          break
        case 'closed':
          res = await listBugs({
            ...buildListParams(),
            status: 'closed,rejected',
          })
          break
        case 'all':
        default:
          res = await listBugs(buildListParams())
          break
      }
      bugs.value = res.results
      total.value = res.count
      syncUrl()
    } catch (e) {
      console.error(e)
      ElMessage.error(extractErrorMessage(e, '加载缺陷列表失败'))
    } finally {
      loading.value = false
    }
  }

  const loadStats = async () => {
    statsLoading.value = true
    try {
      stats.value = await getBugStats(options.projectId)
    } catch (e) {
      console.error(e)
    } finally {
      statsLoading.value = false
    }
  }

  const loadMembers = async () => {
    try {
      projectMembers.value = await getProjectMembers(options.projectId)
    } catch {
      // Non-critical
    }
  }

  const refresh = async () => {
    await Promise.all([loadBugs(), loadStats()])
  }

  const reload = () => {
    page.value = 1
    loadBugs()
  }

  // ── View & Filter ──
  const changeView = (newView: string) => {
    view.value = newView
    page.value = 1
    loadBugs()
    loadStats()
  }

  const updateFilters = (newFilters: BugFilters) => {
    Object.assign(filters, newFilters)
    reload()
  }

  const resetFilters = () => {
    Object.assign(filters, {
      keyword: '',
      status: [],
      severity: [],
      priority: [],
      source_test_type: '',
      assignee: null,
    })
    reload()
  }

  // ── Quick Actions ──
  const applyBugUpdate = (row: BugListItem, updated: any) => {
    Object.assign(row, {
      status: updated.status ?? row.status,
      status_display: updated.status_display ?? row.status_display,
      severity: updated.severity ?? row.severity,
      severity_display: updated.severity_display ?? row.severity_display,
      priority: updated.priority ?? row.priority,
      priority_display: updated.priority_display ?? row.priority_display,
      assignee: updated.assignee ?? row.assignee,
      allowed_transitions: updated.allowed_transitions ?? row.allowed_transitions,
    })
  }

  const handleUpdateSeverity = async (row: BugListItem, severity: BugSeverity) => {
    try {
      const updated = await updateBug(row.id, { severity })
      applyBugUpdate(row, updated)
      ElMessage.success('严重度已更新')
      await loadStats()
    } catch (e) {
      ElMessage.error(extractErrorMessage(e, '保存严重度失败'))
      await loadBugs()
    }
  }

  const handleUpdatePriority = async (row: BugListItem, priority: BugPriority) => {
    try {
      const updated = await updateBug(row.id, { priority })
      applyBugUpdate(row, updated)
      ElMessage.success('优先级已更新')
    } catch (e) {
      ElMessage.error(extractErrorMessage(e, '保存优先级失败'))
      await loadBugs()
    }
  }

  const handleAssign = async (bugId: number, userId: number, comment: string) => {
    try {
      const updated = await assignBug(bugId, userId, comment)
      // Find and update the row
      const idx = bugs.value.findIndex((b) => b.id === bugId)
      if (idx !== -1) {
        applyBugUpdate(bugs.value[idx], updated)
      }
      ElMessage.success('已指派')
      await loadStats()
    } catch (e) {
      ElMessage.error(extractErrorMessage(e, '指派失败'))
      await loadBugs()
    }
  }

  const handleTransition = async (bugId: number, toStatus: string, comment: string) => {
    try {
      const updated = await transitionBug(bugId, toStatus as BugStatus, comment)
      const idx = bugs.value.findIndex((b) => b.id === bugId)
      if (idx !== -1) {
        applyBugUpdate(bugs.value[idx], updated)
      }
      ElMessage.success('状态已更新')
      await loadStats()
    } catch (e) {
      ElMessage.error(extractErrorMessage(e, '流转失败'))
      await loadBugs()
    }
  }

  const handleCreateBug = async (payload: BugCreatePayload): Promise<any> => {
    return await createBug(payload)
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteBug(id)
      ElMessage.success('已删除')
      await refresh()
    } catch (e) {
      ElMessage.error(extractErrorMessage(e, '删除失败'))
    }
  }

  const handleSeedDemo = async () => {
    try {
      const res = await seedDemoBugs(options.projectId)
      ElMessage.success(`已导入 ${res.added} 条示例缺陷`)
      await refresh()
    } catch (e: any) {
      ElMessage.error(extractErrorMessage(e, '导入失败'))
    }
  }

  // ── Empty Text ──
  const emptyText = computed(() => {
    if (loading.value) return ''
    if (bugs.value.length > 0) return ''

    const hasActiveFilters =
      filters.keyword ||
      filters.status.length > 0 ||
      filters.severity.length > 0 ||
      filters.priority.length > 0 ||
      filters.source_test_type ||
      filters.assignee

    if (hasActiveFilters) {
      return '没有符合条件的缺陷，可以清空筛选后重试。'
    }

    switch (view.value) {
      case 'my_pending':
        return '当前没有分配给你的待处理缺陷。'
      case 'reported_by_me':
        return '你还没有提交过缺陷。'
      case 'verifying':
        return '当前没有待验证的缺陷。'
      case 'high_risk':
        return '当前没有高风险缺陷。'
      case 'closed':
        return '当前没有已关闭的缺陷。'
      case 'all':
      default:
        return '当前项目还没有缺陷，可以新建一个缺陷。'
    }
  })

  // ── Init ──
  initFromUrl()
  onMounted(() => {
    loadBugs()
    loadStats()
    loadMembers()
  })

  return {
    // State
    view,
    filters,
    page,
    pageSize,
    total,
    bugs,
    stats,
    loading,
    statsLoading,
    projectMembers,
    isOwner,
    emptyText,

    // Data
    loadBugs,
    loadStats,
    loadMembers,
    refresh,
    reload,

    // View & filter
    changeView,
    updateFilters,
    resetFilters,

    // Actions
    handleUpdateSeverity,
    handleUpdatePriority,
    handleAssign,
    handleTransition,
    handleCreateBug,
    handleDelete,
    handleSeedDemo,
  }
}
