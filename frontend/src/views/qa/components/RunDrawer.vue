<template>
  <el-drawer v-model="visible" :title="`运行：${caseName}`" size="50%" :before-close="handleClose">
    <div class="run-drawer">
      <el-tag v-if="!finished && connected" type="warning">运行中</el-tag>
      <el-tag v-else-if="finished && lastSuccess" type="success">已通过</el-tag>
      <el-tag v-else-if="finished" type="danger">失败</el-tag>
      <el-tag v-else type="info">连接中…</el-tag>

      <div class="steps">
        <div v-for="(step, i) in stepsView" :key="i" class="step" :class="step.status">
          <div class="head">
            <span class="idx">{{ i + 1 }}</span>
            <span class="action">{{ step.action }}</span>
            <span class="desc">{{ step.desc }}</span>
            <el-tag v-if="step.status === 'passed'" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="step.status === 'failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="step.status === 'running'" type="warning" size="small">执行中</el-tag>
          </div>
          <div v-if="step.logs.length" class="logs">
            <pre>{{ step.logs.join('\n') }}</pre>
          </div>
          <div v-if="step.error" class="error">
            <strong>[{{ step.errorCode }}] {{ step.error }}</strong>
            <pre v-if="step.traceback">{{ step.traceback }}</pre>
          </div>
          <img v-if="step.screenshotPath" :src="screenshotUrl(step.screenshotPath)" class="thumb" />
        </div>
      </div>

      <el-button v-if="!finished" type="danger" plain @click="abort">中止</el-button>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useUiRunSocket } from '@/composables/useUiRunSocket'

const props = defineProps<{ modelValue: boolean; taskId: string; caseName: string }>()
const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { events, connected, finished, connect, close } = useUiRunSocket(props.taskId)

watch(() => props.modelValue, (v) => {
  if (v) connect()
  else close()
})

watch(() => props.taskId, (newId, oldId) => {
  if (newId === oldId) return
  if (props.modelValue) {
    close()
    connect()
  }
})

const stepsView = computed(() => {
  const map = new Map<number, any>()
  for (const ev of events.value) {
    const i = ev.index
    if (i == null || i < 0) continue
    if (!map.has(i)) {
      map.set(i, { action: '', desc: '', status: 'running', logs: [], error: '', errorCode: '', traceback: '', screenshotPath: '' })
    }
    const s = map.get(i)
    if (ev.type === 'step_start') {
      s.action = ev.action; s.desc = ev.desc; s.status = 'running'
    } else if (ev.type === 'step_log') {
      s.logs.push(ev.message)
    } else if (ev.type === 'step_screenshot') {
      s.screenshotPath = ev.path
    } else if (ev.type === 'step_done') {
      s.status = ev.success ? 'passed' : 'failed'
      if (!ev.success) {
        s.error = ev.message; s.errorCode = ev.code; s.traceback = ev.traceback
      }
    }
  }
  return Array.from(map.entries()).sort((a, b) => a[0] - b[0]).map(([_, v]) => v)
})

const lastSuccess = computed(() => {
  const fin = events.value.find(e => e.type === 'finished')
  return !!fin?.success
})

function screenshotUrl(path: string) {
  // path 是后端临时目录绝对路径；后端需要提供一个 endpoint 用 task_id+index 获取
  return `/api/qa/ui-run/screenshot/?path=${encodeURIComponent(path)}`
}

function abort() {
  // 后续 Task: 调用 POST /api/qa/ui-cases/runs/{task_id}/abort/
}

function handleClose(done: () => void) { close(); done() }
</script>

<style scoped>
.steps .step { padding: 8px; border: 1px solid #eee; margin: 8px 0; }
.step.passed { border-left: 3px solid #67c23a; }
.step.failed { border-left: 3px solid #f56c6c; }
.step.running { border-left: 3px solid #e6a23c; }
.thumb { max-width: 240px; margin-top: 8px; }
.error { color: #f56c6c; }
.error pre { font-size: 11px; max-height: 200px; overflow: auto; }
</style>
