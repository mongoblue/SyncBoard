/**
 * 通用 WebSocket 客户端（观察者模式 + 心跳 + 重连）。
 *
 * 特性：
 *  - 心跳：每 30 秒发 {"type": "ping"} 保活
 *  - 重连：断开 3 秒后自动重连（isExplicitlyClosed 标记用于区分主动/被动断开）
 *  - 消息分发：messageListeners Set 存储回调，onmessage 时广播
 *  - 去重：connect() 时若已连接则跳过
 *
 * 被 boardStore（看板实时同步）使用。notificationStore 和 useRecorderSocket 自己管理 WS。
 */
import { ref } from 'vue';

const isConnected = ref(false);

// 真正的 WebSocket 实例，不需要响应式，所以不用 ref 包裹
let ws: WebSocket | null = null;

// 消息监听器列表 (你的“小本本”)，用 Set 自动去重
const messageListeners = new Set<(data: any) => void>();

// 状态标记与定时器
let isExplicitlyClosed = false; // 用户是否点了“断开”
let reconnectTimer: number | null = null; // 重连倒计时
let heartbeatTimer: number | null = null; // 心跳倒计时

// 配置常量
const RECONNECT_INTERVAL = 3000;  // 3秒重连
const HEARTBEAT_INTERVAL = 30000; // 30秒心跳


const startHeartbeat = () => {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  
  heartbeatTimer = setInterval(() => {
    // 只有连接正常时才发心跳
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, HEARTBEAT_INTERVAL);
};

const stopHeartbeat = () => {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
};

// 🔄 自动重连逻辑
const attemptReconnect = (url: string) => {
  if (isExplicitlyClosed) return; // 如果是用户主动点的断开，就不重连

  console.log(`⏳ 连接断开，${RECONNECT_INTERVAL / 1000}秒后尝试重连...`);
  
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connect(url); // 递归调用 connect
  }, RECONNECT_INTERVAL);
};


const connect = (url: string) => {
  // 🛡️ 卫语句：如果已经连上了，就什么都不做，防止重复创建
  if (ws && ws.readyState === WebSocket.OPEN) return;

  // 创建连接
  ws = new WebSocket(url);

  // ✅ 连接成功
  ws.onopen = () => {
    console.log('🟢 WebSocket 已连接');
    isConnected.value = true; // 改变响应式变量，界面自动更新
    isExplicitlyClosed = false;
    
    startHeartbeat(); // 启动心跳
    if (reconnectTimer) clearTimeout(reconnectTimer); // 清除重连定时器
  };

  // 📩 收到消息 (核心：观察者模式)
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.type === 'pong') return;

      // 📢 广播：遍历小本本，通知所有订阅者
      messageListeners.forEach((listener) => listener(data));
    } catch (e) {
      console.error('❌ 消息解析失败:', e);
    }
  };

  // 🔴 连接关闭
  ws.onclose = (event) => {
    console.log('🔴 WebSocket 已断开', event.code);
    isConnected.value = false;
    stopHeartbeat();
    ws = null; // 清理引用

    // 尝试重连
    attemptReconnect(url);
  };
  
  ws.onerror = (error) => {
    console.error('⚠️ WebSocket 错误:', error);
    // 错误通常会导致 onclose，重连逻辑交给 onclose 处理
  };
};

const send = (msg: any) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  } else {
    console.warn('⚠️ 发送失败：连接未就绪');
  }
};

// 主动关闭 (比如退出登录)
const close = () => {
  isExplicitlyClosed = true; // 标记为主动关闭
  if (ws) ws.close();
};

// 添加/移除 监听器
const addMessageListener = (callback: (data: any) => void) => {
  messageListeners.add(callback);
};
const removeMessageListener = (callback: (data: any) => void) => {
  messageListeners.delete(callback);
};

// 🌟 最终导出给组件使用的函数
export function useWebSocket() {
  return {
    isConnected, // 这是一个 ref，组件里可以用来做 v-if 或者显示状态颜色
    connect,
    send,
    close,
    addMessageListener,
    removeMessageListener
  };
}