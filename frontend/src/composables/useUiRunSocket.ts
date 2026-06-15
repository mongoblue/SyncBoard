import { ref, onUnmounted } from 'vue'

export interface RunEvent {
  type: string
  index?: number
  action?: string
  desc?: string
  message?: string
  success?: boolean
  code?: string
  path?: string
  summary?: { passed: number; failed: number; total: number }
  [key: string]: any
}

export function useUiRunSocket(taskId: string) {
  const events = ref<RunEvent[]>([])
  const connected = ref(false)
  const finished = ref(false)
  const ws = ref<WebSocket | null>(null)

  function connect() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/qa/run/${taskId}/`
    const socket = new WebSocket(url)
    ws.value = socket
    socket.onopen = () => { connected.value = true }
    socket.onclose = () => { connected.value = false }
    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        events.value.push(data)
        if (data.type === 'finished' || data.type === 'run_finished_persisted') {
          finished.value = true
        }
      } catch (e) {}
    }
  }

  function close() {
    ws.value?.close()
    ws.value = null
  }

  onUnmounted(close)

  return { events, connected, finished, connect, close }
}
