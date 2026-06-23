<template>
  <div class="editable-text">
    <pre
      v-if="!editing"
      class="editable-text__display"
      :class="{ 'is-empty': !modelValue }"
      @click="enterEdit"
    >{{ modelValue || placeholder }}</pre>
    <textarea
      v-else
      ref="textareaRef"
      v-model="draft"
      class="editable-text__input"
      :rows="rows"
      :placeholder="placeholder"
      @blur="commit"
      @keydown="onKeydown"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  rows?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'save', v: string): void
}>()

const editing = ref(false)
const draft = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const enterEdit = async () => {
  draft.value = props.modelValue
  editing.value = true
  await nextTick()
  textareaRef.value?.focus()
}

const commit = () => {
  if (!editing.value) return
  const value = draft.value
  editing.value = false
  if (value !== props.modelValue) {
    emit('update:modelValue', value)
    emit('save', value)
  }
}

const onKeydown = (e: KeyboardEvent) => {
  // 兼容 @vue/test-utils 的 trigger('keydown.esc') 简写
  if (e.key === 'Escape' || e.key === 'esc') {
    e.preventDefault()
    editing.value = false
  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    ;(e.target as HTMLTextAreaElement).blur()
  }
}
</script>

<style scoped>
.editable-text { width: 100%; }
.editable-text__display {
  white-space: pre-wrap;
  font-family: inherit;
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  min-height: 24px;
  color: var(--color-text);
}
.editable-text__display:hover {
  background: var(--color-surface-hover);
}
.editable-text__display.is-empty {
  color: var(--color-text-tertiary);
  font-style: italic;
}
.editable-text__input {
  width: 100%;
  font-family: inherit;
  font-size: inherit;
  padding: 6px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  resize: vertical;
  background: var(--color-surface);
  color: var(--color-text);
  transition: box-shadow var(--transition-fast), border-color var(--transition-fast);
}
.editable-text__input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}
</style>
