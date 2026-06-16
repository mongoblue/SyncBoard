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
        <el-button size="small" link @click="emit('append-step', ev)">追加</el-button>
        <el-button size="small" link @click="emit('replace-step', ev, i)">替换</el-button>
      </div>
    </div>

    <div class="actions">
      <el-button @click="emit('replace-all', recordEvents)" :disabled="!recordEvents.length">替换当前用例步骤</el-button>
      <el-button @click="emit('append-all', recordEvents)" :disabled="!recordEvents.length">追加到当前用例</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRecorderSocket } from '@/composables/useRecorderSocket'

const props = defineProps<{ defaultUrl?: string }>()
const emit = defineEmits(['append-step', 'replace-step', 'replace-all', 'append-all', 'panel-stopped'])

const urlInput = ref(props.defaultUrl || '')
const { events, status, lastError, start, stop, pause, resume } = useRecorderSocket()

const recording = computed(() => status.value === 'recording' || status.value === 'paused')
const statusTagType = computed(() => ({
  idle: 'info', connecting: 'warning', recording: 'success',
  paused: 'warning', stopped: 'info', error: 'danger'
}[status.value] || 'info'))
const statusLabel = computed(() => ({
  idle: '空闲', connecting: '连接中', recording: '录制中',
  paused: '已暂停', stopped: '已停止', error: '错误'
}[status.value] || ''))

const recordEvents = computed(() => events.value
  .filter(e => e.type === 'record_event' || e.type === 'record_assert_event')
  .map(e => e.data)
)

function onStart() { start(urlInput.value) }
function onPause() { pause() }
function onResume() { resume() }
function onStop() { emit('panel-stopped'); stop() }
</script>

<style scoped>
.recorder-panel { display: flex; flex-direction: column; gap: 12px; }
.bar { display: flex; gap: 8px; align-items: center; }
.event-list { max-height: 320px; overflow: auto; border: 1px solid #eee; padding: 8px; }
.ev-item { display: flex; gap: 8px; padding: 4px; border-bottom: 1px dashed #f0f0f0; font-size: 12px; }
</style>
