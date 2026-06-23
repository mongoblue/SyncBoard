/**
 * SyncBoard 前端入口。
 * 全局注册顺序：Pinia → Vue Router → Element Plus（含全部图标）→ 自定义指令（v-permission）。
 */
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import './styles/global.css'
import './styles/components.css'
import './styles/element-overrides.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { setupDirectives } from './directives'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(ElementPlus)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册自定义指令
setupDirectives(app)

app.mount('#app')
