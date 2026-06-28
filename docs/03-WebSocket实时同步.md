# WebSocket 实时同步文档

## 1. WebSocket 架构概述

### 1.1 为什么使用 WebSocket

| 特性 | HTTP轮询 | WebSocket |
|------|----------|-----------|
| 实时性 | 依赖轮询间隔 | 真正的实时推送 |
| 延迟 | 数百毫秒到数秒 | 毫秒级 |
| 服务器压力 | 高（频繁请求） | 低（长连接） |
| 带宽消耗 | 高（HTTP头开销） | 低（仅数据帧） |
| 双向通信 | 客户端单向 | 全双工 |

### 1.2 本项目 WebSocket 应用场景

```
┌─────────────────────────────────────────────────────────────┐
│                      WebSocket 应用场景                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 看板实时同步 (board_{project_id})                        │
│     ├── 任务拖拽同步                                        │
│     ├── 任务增删改                                          │
│     ├── 列增删改                                            │
│     └── 用户在线状态                                        │
│                                                             │
│  2. 测试日志推送 (qa_dashboard)                              │
│     ├── 实时测试日志                                        │
│     ├── 测试进度更新                                        │
│     └── 测试结果通知                                        │
│                                                             │
│  3. 全局通知 (system_broadcast)                              │
│     ├── 系统公告                                            │
│     └── 广播消息                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 后端实现 (Django Channels)

### 2.1 ASGI 配置

```python
# backend/asgi.py

import os
from django.core.asgi import get_asgi_application

# 1. 先设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 2. 【关键】先初始化 Django ASGI 应用
# 这步必须在导入 room.routing 之前！
django_asgi_app = get_asgi_application()

# 3. 然后再导入路由
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import room.routing

application = ProtocolTypeRouter({
    # HTTP 请求走 Django 原生 ASGI
    "http": django_asgi_app,
    
    # WebSocket 请求走 Channels
    "websocket": AuthMiddlewareStack(
        URLRouter(
            room.routing.websocket_urlpatterns
        )
    ),
})
```

**关键点：**
- `get_asgi_application()` 必须在导入路由之前调用
- `AuthMiddlewareStack` 提供用户认证支持
- `ProtocolTypeRouter` 根据协议类型分发请求

### 2.2 路由配置

```python
# room/routing.py

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 看板实时同步
    re_path(r'ws/board/(?P<project_id>[^/]+)/$', consumers.BoardConsumer.as_asgi()),
    
    # 聊天室
    re_path(r'ws/chat/(?P<room_name>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    
    # 全局通知
    re_path(r'ws/notifications/$', consumers.GlobalNotificationConsumer.as_asgi()),
    
    # QA测试日志
    re_path(r'ws/qa/dashboard/$', consumers.QADashboardConsumer.as_asgi()),
]
```

### 2.3 消费者实现

#### BoardConsumer (看板消费者)

```python
# room/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. 从 URL 路由参数获取 project_id
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        
        # 2. 构建房间组名
        self.room_group_name = f'board_{self.project_id}'
        
        # 3. 获取当前用户
        self.user = self.scope['user']
        
        # 4. 加入房间组
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # 5. 接受连接
        await self.accept()
        
        # 6. 广播用户加入消息
        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',
                    'message': {
                        'action': 'user_joined',
                        'user': {
                            'id': self.user.id,
                            'username': self.user.username,
                        }
                    }
                }
            )
    
    async def disconnect(self, close_code):
        # 1. 离开房间组
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        # 2. 广播用户离开消息
        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',
                    'message': {
                        'action': 'user_left',
                        'user_id': self.user.id
                    }
                }
            )
    
    async def receive(self, text_data):
        # 接收前端消息
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'move_task':
            # 处理任务移动
            await self.handle_task_move(data)
        elif action == 'update_task':
            # 处理任务更新
            await self.handle_task_update(data)
    
    async def board_update(self, event):
        # 【关键】这个方法名必须和 group_send 中的 'type' 对应
        # Channels 会自动把 'board.update' 转换为 'board_update'
        message = event['message']
        
        # 发送给 WebSocket
        await self.send(text_data=json.dumps({
            'data': message,
            'action': message.get('action')
        }))
```

**核心概念解释：**

| 概念 | 说明 |
|------|------|
| `channel_name` | 每个连接的唯一标识，自动分配 |
| `room_group_name` | 房间组名，相同组的连接会收到相同消息 |
| `channel_layer` | 底层通信层，本项目使用 Redis |
| `group_add` | 将当前连接加入组 |
| `group_discard` | 将当前连接移出组 |
| `group_send` | 向组内所有连接广播消息 |

#### QA Dashboard Consumer (测试日志消费者)

```python
# qa_center/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class QADashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'qa_dashboard'
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def test_log(self, event):
        # 接收测试日志并推送给前端
        await self.send(text_data=json.dumps({
            'type': 'log',
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': event.get('timestamp')
        }))
    
    async def test_progress(self, event):
        # 接收进度更新
        await self.send(text_data=json.dumps({
            'type': 'progress',
            'current': event['current'],
            'total': event['total'],
            'percentage': event['percentage']
        }))
```

### 2.4 Channel Layer 配置

```python
# backend/settings.py

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.environ.get('REDIS_HOST', '127.0.0.1'), 6379)],
        },
    },
}
```

**Redis Channel Layer 工作原理：**

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  用户A连接   │◄───►│             │◄───►│  用户B连接   │
│  channel_1  │     │    Redis    │     │  channel_2  │
└─────────────┘     │   Channel   │     └─────────────┘
                    │   Layer     │
                    │             │
                    │  group_add  │
                    │  group_send │
                    │  group_discard
                    └─────────────┘
```

---

## 3. 前端实现 (Vue3 + 组合式函数)

### 3.1 useWebSocket 组合式函数

```typescript
// src/stores/composables/useWebSocket.ts

import { ref } from 'vue';

const isConnected = ref(false);
let ws: WebSocket | null = null;
const messageListeners = new Set<(data: any) => void>();

// 配置常量
const RECONNECT_INTERVAL = 3000;   // 3秒重连
const HEARTBEAT_INTERVAL = 30000;  // 30秒心跳

let isExplicitlyClosed = false;
let reconnectTimer: number | null = null;
let heartbeatTimer: number | null = null;

/**
 * 启动心跳
 */
const startHeartbeat = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    
    heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, HEARTBEAT_INTERVAL);
};

/**
 * 停止心跳
 */
const stopHeartbeat = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
};

/**
 * 尝试重连
 */
const attemptReconnect = (url: string) => {
    if (isExplicitlyClosed) return;
    
    console.log(`⏳ 连接断开，${RECONNECT_INTERVAL / 1000}秒后尝试重连...`);
    
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
        connect(url);
    }, RECONNECT_INTERVAL);
};

/**
 * 建立 WebSocket 连接
 */
const connect = (url: string) => {
    // 防止重复创建
    if (ws && ws.readyState === WebSocket.OPEN) return;
    
    ws = new WebSocket(url);
    
    ws.onopen = () => {
        console.log('🟢 WebSocket 已连接');
        isConnected.value = true;
        isExplicitlyClosed = false;
        startHeartbeat();
        if (reconnectTimer) clearTimeout(reconnectTimer);
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            // 忽略心跳响应
            if (data.type === 'pong') return;
            
            // 广播给所有监听器（观察者模式）
            messageListeners.forEach((listener) => listener(data));
        } catch (e) {
            console.error('❌ 消息解析失败:', e);
        }
    };
    
    ws.onclose = (event) => {
        console.log('🔴 WebSocket 已断开', event.code);
        isConnected.value = false;
        stopHeartbeat();
        ws = null;
        attemptReconnect(url);
    };
    
    ws.onerror = (error) => {
        console.error('⚠️ WebSocket 错误:', error);
    };
};

/**
 * 发送消息
 */
const send = (msg: any) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    } else {
        console.warn('⚠️ 发送失败：连接未就绪');
    }
};

/**
 * 主动关闭连接
 */
const close = () => {
    isExplicitlyClosed = true;
    if (ws) ws.close();
};

/**
 * 添加消息监听器
 */
const addMessageListener = (callback: (data: any) => void) => {
    messageListeners.add(callback);
};

/**
 * 移除消息监听器
 */
const removeMessageListener = (callback: (data: any) => void) => {
    messageListeners.delete(callback);
};

/**
 * 导出组合式函数
 */
export function useWebSocket() {
    return {
        isConnected,        // 连接状态（响应式）
        connect,            // 连接方法
        send,               // 发送方法
        close,              // 关闭方法
        addMessageListener, // 添加监听器
        removeMessageListener // 移除监听器
    };
}
```

### 3.2 在看板中使用 WebSocket

```typescript
// src/stores/Board.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useWebSocket } from './composables/useWebSocket';

export const useBoardStore = defineStore('board', () => {
    const columns = ref<BoardColumn[]>([]);
    const currentProjectId = ref<string>('');
    
    const { connect, addMessageListener, isConnected } = useWebSocket();
    
    /**
     * 处理 WebSocket 消息
     */
    const handleSocketMessage = (payload: WebSocketMessage): void => {
        const { action, user } = payload.data || payload;
        
        switch (action) {
            case 'user_joined':
                ElMessage.success(`${user.username} 进入了看板`);
                break;
            case 'user_left':
                // 用户离开
                break;
            case 'refresh':
                // 刷新看板数据
                fetchColumns(currentProjectId.value);
                break;
            case 'task_moved':
                // 任务被移动，更新本地状态
                updateLocalTaskPosition(payload.data);
                break;
        }
    };
    
    /**
     * 初始化 WebSocket
     */
    const initSocket = (projectId: string): void => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/board/${projectId}/`;
        
        connect(wsUrl);
        addMessageListener(handleSocketMessage);
    };
    
    /**
     * 移动任务（发送 WebSocket 消息）
     */
    const moveTask = async (taskId: string, targetColumnId: string, position: number) => {
        // 1. 先调用 API 更新数据库
        await service.patch(`/tasks/${taskId}/`, {
            column: targetColumnId,
            position: position
        });
        
        // 2. 发送 WebSocket 消息通知其他用户
        // 注意：实际项目中，API 更新后由后端广播更合适
    };
    
    return {
        columns,
        isConnected,
        initSocket,
        moveTask
    };
});
```

### 3.3 Board.vue 组件中使用

```vue
<template>
    <div class="board">
        <!-- 连接状态指示器 -->
        <div class="connection-status" :class="{ connected: isConnected }">
            {{ isConnected ? '已连接' : '未连接' }}
        </div>
        
        <!-- 看板列 -->
        <draggable
            v-model="columns"
            group="columns"
            @change="handleColumnChange"
        >
            <template #item="{ element: column }">
                <BoardColumn :column="column">
                    <draggable
                        v-model="column.tasks"
                        group="tasks"
                        @change="(e) => handleTaskChange(e, column)"
                    >
                        <template #item="{ element: task }">
                            <TaskCard :task="task" />
                        </template>
                    </draggable>
                </BoardColumn>
            </template>
        </draggable>
    </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { useBoardStore } from '@/stores/Board';
import { storeToRefs } from 'pinia';

const boardStore = useBoardStore();
const { columns, isConnected } = storeToRefs(boardStore);

const props = defineProps<{
    projectId: string;
}>();

onMounted(() => {
    // 初始化 WebSocket 连接
    boardStore.initSocket(props.projectId);
    
    // 获取看板数据
    boardStore.fetchColumns(props.projectId);
});

onUnmounted(() => {
    // 组件卸载时关闭连接
    boardStore.closeSocket();
});

const handleTaskChange = (event: any, column: BoardColumn) => {
    if (event.added) {
        const task = event.added.element;
        const newIndex = event.added.newIndex;
        
        // 计算新位置
        const position = calculatePosition(column.tasks, newIndex);
        
        // 更新任务
        boardStore.moveTask(task.id, column.id, position);
    }
};
</script>
```

---

## 4. 消息协议设计

### 4.1 客户端 → 服务器

```typescript
// 任务移动
{
    action: 'move_task',
    task_id: 'uuid-string',
    target_column_id: 'uuid-string',
    position: 15000.5
}

// 任务更新
{
    action: 'update_task',
    task_id: 'uuid-string',
    data: {
        title: '新标题',
        content: '新内容'
    }
}

// 心跳
{
    type: 'ping'
}
```

### 4.2 服务器 → 客户端

```typescript
// 用户加入
{
    action: 'user_joined',
    user: {
        id: 1,
        username: '张三'
    }
}

// 用户离开
{
    action: 'user_left',
    user_id: 1
}

// 看板刷新
{
    action: 'refresh'
}

// 任务移动通知
{
    action: 'task_moved',
    task_id: 'uuid-string',
    source_column_id: 'uuid-string',
    target_column_id: 'uuid-string',
    position: 15000.5
}

// 测试日志
{
    type: 'log',
    message: '开始执行测试...',
    level: 'info',
    timestamp: '2026-02-09T10:30:00Z'
}

// 心跳响应
{
    type: 'pong'
}
```

---

## 5. 高级特性

### 5.1 用户认证

```python
# 在消费者中获取用户信息

class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 通过 AuthMiddlewareStack，用户信息在 scope 中
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            # 未认证，拒绝连接
            await self.close()
            return
        
        # 检查用户是否有权限访问该项目
        project_id = self.scope['url_route']['kwargs']['project_id']
        has_permission = await self.check_permission(project_id)
        
        if not has_permission:
            await self.close()
            return
        
        await self.accept()
```

### 5.2 房间管理

```python
# 获取房间内的所有连接
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()

# 发送消息到特定房间
await channel_layer.group_send(
    'board_project_123',
    {
        'type': 'board_update',
        'message': {...}
    }
)

# 发送消息到多个房间
for project_id in project_ids:
    await channel_layer.group_send(
        f'board_{project_id}',
        {'type': 'board_update', 'message': {...}}
    )
```

### 5.3 错误处理

```typescript
// 前端错误处理
const connect = (url: string) => {
    try {
        ws = new WebSocket(url);
        
        ws.onerror = (error) => {
            console.error('WebSocket 错误:', error);
            // 记录错误日志
            logError('websocket_error', error);
        };
        
        ws.onclose = (event) => {
            if (event.code === 1006) {
                // 异常关闭，可能是服务器问题
                console.error('连接异常关闭');
            } else if (event.code === 1000) {
                // 正常关闭
                console.log('连接正常关闭');
            }
            
            // 尝试重连
            if (!isExplicitlyClosed) {
                attemptReconnect(url);
            }
        };
    } catch (error) {
        console.error('创建 WebSocket 失败:', error);
    }
};
```

---

## 6. 性能优化

### 6.1 连接池管理

```python
# 使用 Redis 连接池
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": ["redis://localhost:6379/0"],
            "capacity": 1500,  # 通道容量
            "expiry": 10,      # 消息过期时间（秒）
        },
    },
}
```

### 6.2 消息压缩

```python
# 对于大量数据，考虑压缩
import gzip
import base64

async def send_compressed(self, data):
    compressed = gzip.compress(json.dumps(data).encode())
    encoded = base64.b64encode(compressed).decode()
    await self.send(text_data=encoded)
```

### 6.3 批量更新

```python
# 避免频繁发送小消息，考虑批量
class BoardConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending_updates = []
        self.batch_timer = None
    
    async def queue_update(self, update):
        self.pending_updates.append(update)
        
        # 100ms 内批量发送
        if not self.batch_timer:
            self.batch_timer = asyncio.create_task(self.send_batch())
    
    async def send_batch(self):
        await asyncio.sleep(0.1)
        
        if self.pending_updates:
            await self.send(text_data=json.dumps({
                'action': 'batch_update',
                'updates': self.pending_updates
            }))
            self.pending_updates = []
        
        self.batch_timer = None
```

---

## 7. 调试技巧

### 7.1 浏览器调试

```javascript
// 在浏览器控制台查看 WebSocket
// 1. 打开 Network 面板
// 2. 选择 WS (WebSocket) 过滤器
// 3. 查看消息收发

// 手动发送测试消息
ws = new WebSocket('ws://localhost:8000/ws/board/123/');
ws.onmessage = (e) => console.log('收到:', JSON.parse(e.data));
ws.send(JSON.stringify({action: 'test'}));
```

### 7.2 后端调试

```python
# 添加日志
import logging

logger = logging.getLogger('channels')

class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info(f"用户 {self.user} 连接到房间 {self.room_group_name}")
        ...
    
    async def receive(self, text_data):
        logger.debug(f"收到消息: {text_data}")
        ...
```

### 7.3 Redis 监控

```bash
# 监控 Redis 中的频道
redis-cli monitor | grep -E "(subscribe|publish|group)"

# 查看当前连接数
redis-cli info clients

# 查看频道列表
redis-cli pubsub channels
```

---

## 8. 扩展阅读

- [01-项目架构.md](./01-项目架构.md) - 项目整体架构
- [02-数据模型.md](./02-数据模型.md) - 数据模型设计
- [04-搜索系统.md](./04-搜索系统.md) - 搜索系统实现
- [05-AI助手RAG.md](./05-AI助手RAG.md) - AI助手实现
- [06-质量中心.md](./06-质量中心.md) - 质量中心实现
- [07-前端状态管理.md](./07-前端状态管理.md) - 前端状态管理
- [08-开发调试指南.md](./08-开发调试指南.md) - 开发调试技巧
