/**
 * UI 录制器 WebSocket 状态机。
 *
 * 状态：idle → connecting → recording | paused | stopped | error
 *
 * 连接 ws/qa/recorder/，双向通信：
 *  上游指令：start_recording / stop_recording / pause_recording / resume_recording / run_step
 *  下游事件：recording_started / recording_stopped / step_recorded / step_run_done / error
 *
 * 被 UiCaseDetail.vue 中的 RecorderPanel.vue 使用。
 */
import { ref, onUnmounted } from 'vue'
import { buildWsUrl } from './wsHost'

export interface RecorderEvent {
  type: string
  data?: any
  message?: string
  code?: string
  success?: boolean
}

export interface RecorderSocketOptions {
  projectId?: string | number | null
}

export function useRecorderSocket(options: RecorderSocketOptions = {}) {
  const events = ref<RecorderEvent[]>([])
  const status = ref<'idle' | 'connecting' | 'recording' | 'paused' | 'stopped' | 'error'>('idle')
  const lastError = ref<{ code: string; message: string } | null>(null)
  const lastStepRun = ref<RecorderEvent | null>(null)
  const ws = ref<WebSocket | null>(null)
  const projectId = options.projectId == null || options.projectId === '' ? '' : String(options.projectId)

  function open() {
    if (ws.value) return
    const path = projectId
      ? `/ws/qa/recorder/${encodeURIComponent(projectId)}/`
      : '/ws/qa/recorder/'
    const sock = new WebSocket(buildWsUrl(path))
    ws.value = sock
    status.value = 'connecting'
    sock.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        events.value.push(ev)
        switch (ev.type) {
          case 'recording_started': status.value = 'recording'; break
          case 'recording_paused': status.value = 'paused'; break
          case 'recording_resumed': status.value = 'recording'; break
          case 'recording_stopped': status.value = 'stopped'; break
          case 'step_run_done': lastStepRun.value = ev; break
          case 'error':
            status.value = 'error'
            lastError.value = { code: ev.code || '', message: ev.message || '' }
            break
        }
      } catch {}
    }
    sock.onclose = () => { ws.value = null }
  }

  function send(msg: any) {
    ws.value?.send(JSON.stringify(msg))
  }

  function withProject(payload: Record<string, any>) {
    return projectId ? { ...payload, project_id: projectId } : payload
  }

  function start(url: string, viewport?: { width: number; height: number }) {
    open()
    setTimeout(() => send(withProject({ command: 'start_recording', url, viewport })), 100)
  }
  function stop() { send({ command: 'stop_recording' }) }
  function pause() { send({ command: 'pause_recording' }) }
  function resume() { send({ command: 'resume_recording' }) }
  function runStep(step: any) { send(withProject({ command: 'run_step', step })) }
  function close() {
    try { send({ command: 'stop_recording' }) } catch { /* ignore */ }
    ws.value?.close()
    ws.value = null
  }

  onUnmounted(close)

  return { events, status, lastError, lastStepRun, start, stop, pause, resume, runStep, close }
}
