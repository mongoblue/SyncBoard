import { describe, it, expect } from 'vitest'
import { extractErrorMessage } from '@/utils/error'

describe('extractErrorMessage', () => {
  it('returns detail from response.data.detail first', () => {
    const err = { response: { data: { detail: '权限不足' } } }
    expect(extractErrorMessage(err)).toBe('权限不足')
  })

  it('falls back to response.data.error when no detail', () => {
    const err = { response: { data: { error: '状态非法' } } }
    expect(extractErrorMessage(err)).toBe('状态非法')
  })

  it('falls back to err.message when no response', () => {
    const err = { message: 'Network Error' }
    expect(extractErrorMessage(err)).toBe('Network Error')
  })

  it('returns fallback string when nothing usable', () => {
    expect(extractErrorMessage({}, '默认失败')).toBe('默认失败')
  })

  it('detail wins over error when both present', () => {
    const err = { response: { data: { detail: '主', error: '次' } } }
    expect(extractErrorMessage(err)).toBe('主')
  })
})
