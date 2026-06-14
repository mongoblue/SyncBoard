import type { Directive, DirectiveBinding } from 'vue';
import { watchEffect } from 'vue';
import { useAuthStore } from '@/stores/Auth';

function checkAndToggle(
  el: HTMLElement,
  required: string[],
  mode: 'some' | 'every'
) {
  const authStore = useAuthStore();
  const hasPermission = mode === 'every'
    ? required.every(p => authStore.permissions.includes(p))
    : required.some(p => authStore.permissions.includes(p));

  // 使用 display:none 而非 removeChild，权限变化后可恢复
  if (hasPermission) {
    el.style.display = '';
    el.removeAttribute('data-permission-hidden');
  } else {
    el.style.display = 'none';
    el.setAttribute('data-permission-hidden', 'true');
  }
}

function resolvePermissions(value: string | string[] | undefined): string[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

const permission: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
    const required = resolvePermissions(binding.value);
    // 初始检查
    checkAndToggle(el, required, 'some');
    // 响应式：权限加载后自动更新
    const stop = watchEffect(() => {
      checkAndToggle(el, required, 'some');
    });
    (el as any)._permissionStop = stop;
  },
  unmounted(el: HTMLElement) {
    (el as any)._permissionStop?.();
  },
};

export const permissionAll: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string[]>) {
    const required = resolvePermissions(binding.value);
    const stop = watchEffect(() => {
      checkAndToggle(el, required, 'every');
    });
    (el as any)._permissionStop = stop;
  },
  unmounted(el: HTMLElement) {
    (el as any)._permissionStop?.();
  },
};

export const permissionAny: Directive = {
  mounted(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
    const required = resolvePermissions(binding.value);
    const stop = watchEffect(() => {
      checkAndToggle(el, required, 'some');
    });
    (el as any)._permissionStop = stop;
  },
  unmounted(el: HTMLElement) {
    (el as any)._permissionStop?.();
  },
};

export default permission;
