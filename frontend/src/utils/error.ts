/**
 * 从 axios 错误对象里抽取可读的错误消息
 * 优先级: response.data.detail > response.data.error > err.message > fallback
 */
export function extractErrorMessage(e: any, fallback = '操作失败'): string {
  return e?.response?.data?.detail
      || e?.response?.data?.error
      || e?.message
      || fallback
}
