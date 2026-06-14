import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

describe('Example Test Suite', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should pass basic assertion', () => {
    expect(true).toBe(true)
  })

  it('should handle async operations', async () => {
    const promise = Promise.resolve('test')
    const result = await promise
    expect(result).toBe('test')
  })

  it('should mock functions correctly', () => {
    const mockFn = vi.fn()
    mockFn('hello')
    expect(mockFn).toHaveBeenCalledWith('hello')
  })
})
