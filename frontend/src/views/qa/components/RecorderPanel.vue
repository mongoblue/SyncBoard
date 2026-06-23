<template>
  <div class="recorder-panel">
    <div class="bar">
      <el-input v-model="urlInput" placeholder="录制起始 URL" :disabled="recording" />
      <el-button v-if="!recording" type="primary" @click="onStart">开始录制</el-button>
      <el-button v-else type="warning" @click="onPause" v-show="status === 'recording'">暂停</el-button>
      <el-button v-show="status === 'paused'" type="primary" @click="onResume">恢复</el-button>
      <el-button v-if="recording" type="danger" @click="onStop">停止</el-button>
      <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
    </div>

    <el-alert v-if="lastError" type="error" :closable="false">
      <template #title>[{{ lastError.code }}] {{ lastError.message }}</template>
    </el-alert>

    <div class="event-list">
      <div v-for="(ev, i) in recordEvents" :key="i" class="ev-item">
        <span class="action">{{ ev.action }}</span>
        <span class="selector">{{ ev.selector }}</span>
        <span class="value">{{ ev.value }}</span>
        <el-button size="small" link @click="onTryStep(ev)">试运行</el-button>
        <el-button size="small" link @click="emit('append-step', ev)">追加</el-button>
        <el-button size="small" link @click="emit('replace-step', ev, i)">替换</el-button>
      </div>
    </div>

    <div class="actions">
      <el-button @click="emit('replace-all', recordEvents)" :disabled="!recordEvents.length">替换当前用例步骤</el-button>
      <el-button @click="emit('append-all', recordEvents)" :disabled="!recordEvents.length">追加到当前用例</el-button>
    </div>

    <div v-if="status === 'stopped'" class="footer-actions">
      <el-button type="success" :disabled="!recordEvents.length" @click="onComplete">
        完成并关闭（自动追加 {{ recordEvents.length }} 条）
      </el-button>
      <el-button @click="onDiscard">放弃录制并关闭</el-button>
    </div>

    <el-dialog v-model="assertDialogVisible" title="选择断言类型" width="420px">
      <template v-if="pendingAssert">
        <el-form label-width="80px" size="small">
          <el-form-item label="目标">
            <el-input :model-value="pendingAssert.selector" disabled />
          </el-form-item>
          <el-form-item label="断言类型">
            <el-radio-group v-model="pendingAssert.action">
              <el-radio label="assert_visible">元素可见</el-radio>
              <el-radio label="assert_text">文本完全等于</el-radio>
              <el-radio label="assert_contains_text">文本包含</el-radio>
              <el-radio label="assert_attribute">属性等于</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="pendingAssert.action !== 'assert_visible'" :label="pendingAssert.action === 'assert_attribute' ? '属性名' : '期望值'">
            <el-input v-model="pendingAssert.expected_value" :placeholder="pendingAssert.action === 'assert_attribute' ? '如 data-id' : '期望值'" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="assertDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAssert">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRecorderSocket } from '@/composables/useRecorderSocket'

interface PendingAssert {
  action: 'assert_visible' | 'assert_text' | 'assert_contains_text' | 'assert_attribute'
  expected_value: string
  attribute: string
  selector: string
}

const props = defineProps<{ defaultUrl?: string }>()
const emit = defineEmits(['append-step', 'replace-step', 'replace-all', 'append-all', 'panel-stopped'])

const urlInput = ref(props.defaultUrl || '')
const { events, status, lastError, start, stop, pause, resume, runStep } = useRecorderSocket()

const recording = computed(() => status.value === 'recording' || status.value === 'paused')
const statusTagType = computed(() => ({
  idle: 'info', connecting: 'warning', recording: 'success',
  paused: 'warning', stopped: 'info', error: 'danger'
}[status.value] || 'info'))
const statusLabel = computed(() => ({
  idle: '空闲', connecting: '连接中', recording: '录制中',
  paused: '已暂停', stopped: '已停止', error: '错误'
}[status.value] || ''))

const injectedEvents = ref<any[]>([])
const assertDialogVisible = ref(false)
const pendingAssert = ref<PendingAssert | null>(null)

const recordEvents = computed(() => [
  ...events.value
    .filter(e => e.type === 'record_event' || e.type === 'record_assert_event')
    .map(e => e.data),
  ...injectedEvents.value,
])

watch(events, (list) => {
  const last = list[list.length - 1]
  if (!last) return
  if (last.type === 'record_assert_event' && last.data) {
    pendingAssert.value = {
      action: last.data.action || 'assert_visible',
      expected_value: last.data.value || '',
      attribute: last.data.attribute || '',
      selector: last.data.selector || '',
    }
    assertDialogVisible.value = true
  } else if (last.type === 'step_run_done') {
    ElMessage[last.success ? 'success' : 'error'](last.message || '执行完成')
  }
}, { deep: true })

function onStart() { start(urlInput.value) }
function onPause() { pause() }
function onResume() { resume() }
function onStop() { stop() }

function onTryStep(step: any) { runStep(step) }

function onComplete() {
  if (recordEvents.value.length > 0) {
    emit('append-all', recordEvents.value)
  }
  emit('panel-stopped')
}
function onDiscard() { emit('panel-stopped') }

function confirmAssert() {
  if (!pendingAssert.value) return
  const p = pendingAssert.value
  const ev: any = {
    action: p.action,
    selector: p.selector,
    value: '',
  }
  if (p.action === 'assert_attribute') {
    ev.attribute = p.attribute || ''
    ev.value = p.expected_value || ''
  } else if (p.action !== 'assert_visible') {
    ev.value = p.expected_value || ''
  }
  injectedEvents.value.push(ev)
  assertDialogVisible.value = false
  pendingAssert.value = null
}
</script>

<style scoped>
.recorder-panel { display: flex; flex-direction: column; gap: 12px; }
.bar { display: flex; gap: 8px; align-items: center; }
.event-list { max-height: 320px; overflow: auto; border: 1px solid #eee; padding: 8px; }
.ev-item { display: flex; gap: 8px; padding: 4px; border-bottom: 1px dashed #f0f0f0; font-size: 12px; align-items: center; }
.ev-item .selector { flex: 1; word-break: break-all; }
.ev-item .value { color: #888; }
.footer-actions { display: flex; gap: 8px; padding-top: 8px; border-top: 1px solid #eee; }
</style>
