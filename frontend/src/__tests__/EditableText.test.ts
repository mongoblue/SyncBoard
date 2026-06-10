import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EditableText from '@/components/bug/EditableText.vue'

describe('EditableText', () => {
  it('renders readonly pre by default with the value', () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'hello' } })
    expect(wrapper.find('pre').text()).toBe('hello')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })

  it('switches to textarea on click and emits update:modelValue on blur', async () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'hello' } })
    await wrapper.find('pre').trigger('click')
    expect(wrapper.find('textarea').exists()).toBe(true)
    await wrapper.find('textarea').setValue('hello world')
    await wrapper.find('textarea').trigger('blur')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['hello world'])
    expect(wrapper.emitted('save')?.[0]).toEqual(['hello world'])
  })

  it('Escape cancels edit and restores original value', async () => {
    const wrapper = mount(EditableText, { props: { modelValue: 'original' } })
    await wrapper.find('pre').trigger('click')
    await wrapper.find('textarea').setValue('changed')
    await wrapper.find('textarea').trigger('keydown.esc')
    expect(wrapper.find('pre').text()).toBe('original')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('shows placeholder when value is empty', () => {
    const wrapper = mount(EditableText, {
      props: { modelValue: '', placeholder: '（无）' },
    })
    expect(wrapper.find('pre').text()).toBe('（无）')
  })
})
