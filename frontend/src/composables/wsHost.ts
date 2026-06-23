/**
 * 计算 WebSocket 主机地址。
 *
 * dev 环境下直连后端（默认 localhost:8000），绕开 Vite 代理。
 * 原因：vite 的 http-proxy 在 WS 关闭路径会污染浏览器 ↔ vite 的 HTTP keepalive
 * socket pool，导致 UI/性能测试结束后页面所有 HTTP 请求永久 pending。
 *
 * 用 location.hostname 而非硬编码 localhost：用户用 127.0.0.1:5173 进站时，
 * cookie 域是 127.0.0.1，必须配 127.0.0.1:8000 才能带上 sessionid。
 */
export function getWsHost(): string {
  if (import.meta.env.DEV) {
    const port = (import.meta.env.VITE_BACKEND_PORT as string) || '8000'
    return `${window.location.hostname}:${port}`
  }
  return window.location.host
}

export function getWsProtocol(): 'ws:' | 'wss:' {
  return window.location.protocol === 'https:' ? 'wss:' : 'ws:'
}

export function buildWsUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${getWsProtocol()}//${getWsHost()}${normalized}`
}
