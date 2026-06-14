import type { App } from 'vue';
import permission, { permissionAll, permissionAny } from './permission';

// 注册所有指令
export function setupDirectives(app: App) {
  app.directive('permission', permission);
  app.directive('permission-all', permissionAll);
  app.directive('permission-any', permissionAny);
}

export { permission, permissionAll, permissionAny };
export default permission;
