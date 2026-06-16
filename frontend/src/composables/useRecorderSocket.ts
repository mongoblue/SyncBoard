import { ref, onUnmounted } from 'vue'

export interface RecorderEvent {
  type: string
  data?: any
  message?: string
  code?: string
  success?: boolean
}

export function useRecorderSocket() {
  const events = ref<RecorderEvent[]>([])
  const status = ref<'idle' | 'connecting' | 'recording' | 'paused' | 'stopped' | 'error'>('idle')
  const lastError = ref<{ code: string; message: string } | null>(null)
  const lastStepRun = ref<RecorderEvent | null>(null)
  const ws = ref<WebSocket | null>(null)

  function open() {
    if (ws.value) return
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/qa/recorder/`
    const sock = new WebSocket(url)
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

  function start(url: string, viewport?: { width: number; height: number }) {
    open()
    setTimeout(() => send({ command: 'start_recording', url, viewport }), 100)
  }
  function stop() { send({ command: 'stop_recording' }) }
  function pause() { send({ command: 'pause_recording' }) }
  function resume() { send({ command: 'resume_recording' }) }
  function runStep(step: any) { send({ command: 'run_step', step }) }
  function close() { ws.value?.close(); ws.value = null }

  onUnmounted(close)

  return { events, status, lastError, lastStepRun, start, stop, pause, resume, runStep, close }
}
