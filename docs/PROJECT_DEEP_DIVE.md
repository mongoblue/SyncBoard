# SyncBoard 深度拆解

> 单文件、按目录跳转、可对着讲的项目深度文档。
> 文件路径全部为仓库相对路径，方便 IDE `Ctrl+点击` 跳转。

---

## 目录

- [0. 阅读指南 + 全局架构图](#0-阅读指南--全局架构图)
- [1. WebSocket 实时层深度拆解](#1-websocket-实时层深度拆解)
- [2. AI 域深度拆解](#2-ai-域深度拆解)
- [3. QA API 测试执行器深度拆解（新旧两套）](#3-qa-api-测试执行器深度拆解新旧两套)
- [4. UI 测试深度拆解（Playwright 录制 / 回放）](#4-ui-测试深度拆解playwright-录制--回放)
- [5. 性能测试深度拆解（Locust headless）](#5-性能测试深度拆解locust-headless)
- [6. DevOps 平台深度拆解](#6-devops-平台深度拆解)
- [7. 跨模块全景：一次"AI 创建用例并执行"端到端走查](#7-跨模块全景一次ai-创建用例并执行端到端走查)
- [附录 A：UUID vs 自增 ID 表](#附录-auuid-vs-自增-id-表)
- [附录 B：WebSocket 路径 / 群组 / 协议总表](#附录-bwebsocket-路径--群组--协议总表)
- [附录 C：六大模块的"必读 6 文件"](#附录-c六大模块的必读-6-文件)

---

## 0. 阅读指南 + 全局架构图

### 0.1 这份文档的读法

每一章统一四个小节，能独立读、也能顺读：

- **A. 数据流 / 调用链**：从用户动作 → API → 执行器 → 子进程 → WebSocket → 前端渲染的完整箭头图
- **B. 关键代码片段**：核心 10~30 行真实代码，附 `file:line` 引用
- **C. 设计权衡 / 易混点**：为什么这么做、坑在哪、新旧版本差异
- **D. 问答库**：5~8 个硬核问题 + 标准答案；面试 / 答辩用

如果时间紧，建议顺序读 0 → 1 → 7（先全局架构 → 看 WebSocket → 看端到端串讲），再按模块挑选。

### 0.2 整体架构图

```
                                ┌──────────────────────────────────────────┐
                                │              浏览器 (Chrome)              │
                                │   Vue 3 + Vite 5173                       │
                                │   ├─ Pinia stores (board / chat / qa)     │
                                │   ├─ Axios (REST + CSRF)                  │
                                │   ├─ useWebSocket / useRecorderSocket     │
                                │   └─ EventSource (AI 流式)                │
                                └────────────┬─────────────────────────────┘
                                             │
                  ┌──────────────────────────┼───────────────────────────┐
            REST  │                 WebSocket│                       SSE │
         (Axios)  │              (ws + ping) │              (StreamingHTTPResponse)
                  ▼                          ▼                           ▼
              ┌────────────────────────────────────────────────────────────┐
              │  uvicorn ASGI :8000   (HTTP + WebSocket + SSE 同进程)      │
              │  ├─ Django 6 + DRF + drf-spectacular                       │
              │  └─ Channels (URLRouter → AuthMiddlewareStack)             │
              └─────┬─────────────────┬─────────────────┬─────────────────┘
                    │                 │                 │
            ┌───────┘                 │                 └────────┐
            ▼                         ▼                          ▼
      ┌──────────┐            ┌──────────────┐         ┌───────────────┐
      │  MySQL 8 │            │   Redis 7    │         │ Elasticsearch │
      │  业务数据 │            │ Broker /     │         │  Haystack /   │
      │          │            │ Channel /    │         │  Ngram 中文   │
      │          │            │ Cache /Stream│         │  全文检索      │
      └──────────┘            └──────┬───────┘         └───────────────┘
                                     │
                              ┌──────┴───────┐
                              ▼              ▼
                       ┌──────────┐  ┌──────────────────┐
                       │ Celery   │  │ DeepSeek 云端 API │
                       │ Worker   │  │  (兼容 OpenAI)    │
                       │ + Beat   │  └──────────────────┘
                       └──────────┘
                              │
                  ┌───────────┴───────────────────────────┐
                  ▼                                       ▼
        ┌──────────────────┐                    ┌──────────────────┐
        │ Playwright 子进程 │                    │ Locust 子进程    │
        │ recorder_worker  │                    │ headless mode    │
        │ runner_worker    │                    │ 文件 IPC          │
        │ (stdin/stdout    │                    │ (locustfile_     │
        │  JSON Lines)     │                    │  current.py)     │
        └──────────────────┘                    └──────────────────┘
```

### 0.3 关键原则：REST 写数据 + WebSocket 只传"通知"

整个项目最重要的设计原则一句话概括：

> **WebSocket 不当数据通道用，只当通知总线。**
> 客户端收到 `refresh` 事件 → 主动通过 REST 拉最新数据。

这条原则的根据：
- 避免 WS 通道里的 payload 与 DB 写入路径分裂（写入是 REST + Django ORM，WS 不重做一遍）
- 避免在 consumer 里写复杂业务（Channels 的 channel layer 串行处理 group 消息，CPU 密集会拖垮整个 WS）
- 序列化已经在 DRF Serializer 里写过一遍，WS 不重复

唯一的例外：
- **Chat 消息**：直接把渲染后的 message 推过去（chat 数据进 Redis Stream 持久化，不是 MySQL，所以走"WS 直传"+ "Stream 重放" 两条路）
- **录制 / 运行进度**：事件流（如 click / fill / case_done）本身就是流式信号，不存在"再去 REST 拉一次"的意义

### 0.4 关键文件入口

| 关注点 | 文件 |
|---|---|
| 整体配置（INSTALLED_APPS / Channels / Celery） | `backend/backend/settings.py` |
| ASGI 路由（REST + WebSocket 入口） | `backend/backend/asgi.py` |
| WebSocket 路由总表 | `backend/room/routing.py` + `backend/qa_center/routing.py` |
| Celery 任务 | `backend/backend/celery.py` + `backend/backend/tasks.py` |
| 前端入口 | `frontend/src/main.ts` + `frontend/src/router/index.ts` |

---

## 1. WebSocket 实时层深度拆解

### 1.A 数据流 / 调用链

WebSocket 一共 8 条路径（详见附录 B），由 4 个 Django app 提供：

```
浏览器                      Channel Layer (Redis)              业务侧
┌──────────────┐  WS握手    ┌──────────────────┐            ┌─────────────┐
│ useWebSocket │ ─────────→ │ AuthMiddleware    │ ─────────→ │ Consumer    │
│ (单实例)      │            │  Stack            │            │ .connect()  │
│              │            │                   │            │  鉴权         │
│ ws.onmessage │ ←────────── │ group_send        │ ←────────── │ group_add    │
│  → 回调集合   │  广播       │ (XX_layer)        │            │             │
└──────────────┘            └──────────────────┘            └─────────────┘
        ▲                                                          │
        │                                                          ▼
        │            ┌──────────────────────────────────┐    ┌─────────┐
        └────────────│ REST 路径中触发 group_send         │ ←──│ MySQL    │
                     │ (例: 拖卡片 → BoardConsumer.refresh)│    │ ORM 写入 │
                     └──────────────────────────────────┘    └─────────┘
```

**典型时序**：用户 A 在浏览器拖任务从列 A → 列 B
1. 前端 A → `PATCH /api/tasks/{uuid}/move`（REST 写库）
2. Django view 改 Task.column → `async_to_sync(channel_layer.group_send)("board_{project_id}", {"type": "board_update", "data": "refresh"})`
3. Channels 把消息扇出到这个 group 里所有 channel
4. `BoardConsumer.board_update`（`backend/room/consumers.py:111`）被调用 → `self.send(text_data=...)` 发回各客户端
5. 用户 B 浏览器 onmessage → 触发 listener → boardStore 调 REST `GET /api/projects/{id}/board` 拉最新数据 → Vue diff 重渲染

### 1.B 关键代码片段

**前端通用 WebSocket 封装** `frontend/src/stores/composables/useWebSocket.ts:60`：

```typescript
const connect = (url: string) => {
  // 卫语句：已连接则跳过，避免重复创建
  if (ws && ws.readyState === WebSocket.OPEN) return;

  ws = new WebSocket(url);

  ws.onopen = () => {
    isConnected.value = true;
    isExplicitlyClosed = false;
    startHeartbeat();                    // 30s ping
    if (reconnectTimer) clearTimeout(reconnectTimer);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'pong') return;
    messageListeners.forEach((listener) => listener(data));   // 观察者模式广播
  };

  ws.onclose = () => {
    isConnected.value = false;
    stopHeartbeat();
    ws = null;
    attemptReconnect(url);              // 3s 后重连（除非主动 close）
  };
};
```

**心跳与重连** `frontend/src/stores/composables/useWebSocket.ts:32`：

```typescript
const RECONNECT_INTERVAL = 3000;
const HEARTBEAT_INTERVAL = 30000;

const startHeartbeat = () => {
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, HEARTBEAT_INTERVAL);
};

const attemptReconnect = (url: string) => {
  if (isExplicitlyClosed) return;          // 主动断开就不重连
  reconnectTimer = setTimeout(() => connect(url), RECONNECT_INTERVAL);
};
```

**BoardConsumer 鉴权 + group 加入** `backend/room/consumers.py:31`：

```python
async def connect(self):
    self.project_id = self.scope['url_route']['kwargs']['project_id']
    self.group_name = f"board_{self.project_id}"
    user = self.scope['user']
    if user.is_anonymous or not await self._is_project_member(user, self.project_id):
        await self.close(code=4003)       # 非项目成员 → 直接断
        return
    await self.channel_layer.group_add(self.group_name, self.channel_name)
    await self.accept()
```

**服务端触发广播** （以拖任务为例，在 view 里）：

```python
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    f"board_{project_id}",
    {"type": "board_update", "data": "refresh"}
)
```

### 1.C 设计权衡 / 易混点

| 决策 | 为什么 | 副作用 / 坑 |
|---|---|---|
| WS 只发 `refresh`，不发数据 | 避免与 REST 写库路径分裂；序列化只在 DRF 写一次 | 多一次 REST 往返，弱网会卡 |
| 鉴权失败 `close(4003)` 而非 401 | WS 握手完成后 HTTP 状态码已发出，只能用 close code；4000-4999 是应用层自定义区间 | 前端需要识别 4003 区别于 1006（网络断） |
| 心跳 30s | Channels 默认 idle timeout ~60s，30s 留出一倍裕量 | 太频繁会让 channel layer 压力变大 |
| `useWebSocket` 是单例 ws | 看板只需要一条连接，多页面共享 | 录制 / 通知 / 性能监控不用它，各自独立 ws |
| Recorder 用 `recorder_{channel_name}` 私有 group | 每个用户的录制是独立子进程，事件不能串 | 不能多人同时录制同一会话（这是有意为之） |
| BoardConsumer.receive 几乎空壳 | 业务都走 REST，避免 consumer 里写 ORM | 客户端发 `move_task` 实际上只是通知触发广播 |

### 1.D 问答库

**Q1：鉴权失败为什么 close 4003 而不是 401？**
A：HTTP 升级到 WebSocket 后，握手返回 101 Switching Protocols 已经成功了，再发 HTTP 状态码客户端收不到。WebSocket 协议规定 close code 4000-4999 是应用层自定义。4003 在我们这边明确表示"鉴权失败"，前端 onclose 里识别这个 code 就跳登录。

**Q2：一个用户开两个浏览器标签，消息会重复推送吗？**
A：会。每个标签是一个独立的 channel，都加入了同一个 group。group_send 会扇出到所有 channel。但因为客户端拿到的是 `refresh` 信号，再去 REST 拉数据，两个标签独立刷新各自的视图，业务上无副作用。

**Q3：拖一个任务从列 A 到列 B，refresh 是怎么扩散到其他在线用户的？**
A：完整时序见 1.A，关键三步：(1) REST 写库；(2) view 内 `group_send("board_{project_id}")`；(3) Channels Redis layer 把消息扇出到所有 channel，每个客户端 onmessage → 触发 listener → REST 拉数据。

**Q4：如果 Redis 挂了，看板还能拖任务吗？前端会怎么表现？**
A：REST 部分还能写（MySQL 没挂），但 `group_send` 会抛异常或静默失败（取决于 channel layer 实现）。前端 ws.onclose 触发 → 进入 3s 重连循环，UI 显示离线指示。其他用户拖卡片，A 用户视图不会自动刷新，需要手动 F5。

**Q5：心跳 30s 是怎么算的？Channels 默认 idle timeout 是多少？**
A：Channels 的 daphne / uvicorn 默认 idle timeout 大致 60s。心跳取 30s 是留一倍裕量。再快比如 5s 会让 channel layer 压力变大；再慢比如 50s 偶发抖动就被断了。

**Q6：消息发出去客户端没收到（断网瞬间）怎么办？**
A：当前不做补偿。WS 仅是通知，丢一次 `refresh` 影响有限——用户下一次任何动作或者重连成功后会重新拉数据。这是有意接受的妥协（"最终一致" 而不是 "exactly-once"）。

**Q7：为什么 Recorder 不复用 useWebSocket 单例？**
A：录制是一对一的会话流（每个用户一个子进程），事件量大、协议复杂（start/stop/run_step/事件回推），如果共用单例的 messageListeners Set，所有看板事件也会经过录制的 handler，太脏。独立 ws 让 socket 生命周期与录制会话对齐，简单。

---

## 2. AI 域深度拆解

### 2.A 数据流 / 调用链

AI 域有两条入口，**流式 vs 工具调用是互斥的**：

**入口 1：非流式 + Tool Calling**（用于"创建任务" / "跑测试"等动作类请求）

```
前端 AIChat.vue
  └─ POST /api/ai/chat/ {project_id, message}
      └─ AIChatView.post (room/views/ai.py)
          ├─ 鉴权 → 项目成员
          ├─ build_project_context(project_id, message)   # 拼上下文
          ├─ _chat_with_tools(messages, project_id, user) # 最多 3 轮工具循环
          │   ├─ deepseek.chat.completions.create(tools=AVAILABLE_TOOLS)
          │   ├─ resp.tool_calls 存在? → execute_tool(name, args, project_id, user)
          │   │   └─ 把工具结果作为 role="tool" 消息塞回 messages
          │   ├─ 再次 create() → 拿最终 content
          │   └─ tool_rounds < 3 兜底，防死循环
          ├─ 写 AIMessage (用户 + 助手两条)
          └─ Response: {answer, tool_calls_used}
```

**入口 2：流式 SSE，无工具**（用于纯问答）

```
前端 AIChat.vue
  └─ POST /api/ai/chat/stream/
      └─ AIStreamChatView.post
          ├─ get_streaming_answer(prompt) 生成器
          │   └─ deepseek.chat.completions.create(stream=True)
          │       └─ for chunk in resp: yield chunk.choices[0].delta.content
          └─ StreamingHttpResponse(generator, content_type='text/event-stream')
              └─ 每个 chunk 包成 "data: {chunk}\n\n"
```

**`build_project_context` 是什么**（`backend/room/ai_utils.py:75`）：

构造 5~7 个 section 拼到 prompt 里（用 `add_section` 控制总 token 不超阈值）：
1. 项目概览（名称 / 描述 / 成员数）
2. 任务统计（按状态分桶 + 完成列识别）
3. 关键词命中的任务（基于 message 抽词 → ORM filter）
4. 最近测试结果（最近 10 条 TestResult）
5. 最近评论（如果 message 提到具体任务）
6. （可选）API 文档摘要
7. （可选）成员分布

`add_section` 内部用字符数估算 token（中文 ~1.5 char/token），超阈值就截断尾部 section。

### 2.B 关键代码片段

**SYSTEM_PROMPT_FULL** `backend/room/ai_utils.py:31`：

```python
SYSTEM_PROMPT_FULL = """你是 SyncBoard 项目管理助手。
重要约束：
1. 所有任务 / 列 / 项目的 ID 是 UUID 字符串（不是整数），传给工具时原样照搬。
2. 不要编造数据，找不到就如实说。
3. 涉及具体接口时，先调 get_api_docs 工具查文档。
4. 用中文回答，避免 markdown 标题（前端是 plain text 显示）。
"""
```

**Tool 注册表（17 个工具）** `backend/room/ai_utils.py:363`：

```python
AVAILABLE_TOOLS = [
    # 看板类（5）
    {"type": "function", "function": {"name": "create_task",
        "description": "在指定列创建任务",
        "parameters": {"type": "object", "properties": {
            "column_id": {"type": "string", "description": "列的 UUID"},
            "title": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]}
        }, "required": ["column_id", "title"]}}},
    # API 测试类（3）：create_api_test_case / run_api_test_case / list_api_test_cases
    # UI 测试类（3）：generate_ui_steps / create_ui_test_case / run_ui_test_case
    # 测试执行类（2）、CI/CD 类（1）、API 文档（1）、分析类（2）
    # ... 略
]
```

**工具循环** `backend/room/views/ai.py:137`：

```python
def _chat_with_tools(messages, project_id, user, max_rounds=3):
    tool_rounds = 0
    while tool_rounds < max_rounds:
        resp = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=AVAILABLE_TOOLS,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump())

        if not msg.tool_calls:
            return msg.content                   # 收敛了

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = execute_tool(call.function.name, args, project_id, user)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })
        tool_rounds += 1
    return "（已超过工具调用上限）"
```

**5 层异常处理** `backend/room/ai_utils.py:303`：

```python
def get_rag_answer(prompt: str) -> str:
    try:
        resp = deepseek_client.chat.completions.create(...)
        return resp.choices[0].message.content
    except RateLimitError:
        return "AI 服务请求过于频繁，请稍后再试。"
    except AuthenticationError:
        return "AI 服务认证失败，请联系管理员检查 API Key。"
    except APIStatusError as e:
        if e.status_code == 402:
            return "AI 服务账户余额不足，请联系管理员充值。"
        return f"AI 服务返回异常：{e.message}"
    except APIError as e:
        return f"AI 服务调用失败：{str(e)}"
    except Exception as e:
        logger.exception("AI 调用未知异常")
        return "AI 服务暂时不可用，请稍后再试。"
```

**流式生成器** `backend/room/ai_utils.py:340`：

```python
def get_streaming_answer(prompt: str):
    resp = deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": SYSTEM_PROMPT_FULL},
                  {"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in resp:
        content = chunk.choices[0].delta.content
        if content:
            yield content
```

### 2.C 设计权衡 / 易混点

| 决策 | 为什么 | 副作用 |
|---|---|---|
| 流式 vs 工具调用分两条路 | DeepSeek 早期流式 + tool_calls 边界识别复杂，工具产生的 JSON 不能逐字 yield | 用户问"创建任务"走非流式，体验是"等几秒" + 一次性 |
| `tool_rounds < 3` 兜底 | 防止模型反复调工具死循环 | 极少数复杂任务会被截断 |
| Context 直接查 DB 不走 Haystack | ES 挂了 AI 不能挂 | 长文档检索能力差 |
| 自己写 `_extract_keywords` 不用 jieba | 依赖轻 + 答疑场景关键词少 | 长文本检索能力差，复杂中文断词差 |
| 用字符数估 token | 简单够用，中文 ~1.5 char/token | 真实 token 数有 20% 误差 |
| 用 DeepSeek 不用 OpenAI | 成本 + 国内可达 | SDK 复用 `openai` 库（兼容协议） |
| `generate_ui_steps` 返回 sentinel `UI_STEPS_GENERATE\|...` | 在 tool result 里塞自然语言提示，让 AI 自己再调 create_ui_test_case | 是一种 hack，但简化了步骤生成流程 |
| system prompt 强调 "ID 是 UUID" | 前期模型经常返 `column_id: 1` 这种整数，导致下游 ORM 报错 | 现在依然偶发，靠 prompt 约束 |

### 2.D 问答库

**Q1：列出 DeepSeek 调用的 5 种异常处理。**
A：见 `ai_utils.py:303`。RateLimitError → "请求过频"；AuthenticationError → "API Key 失效"；APIStatusError 402 → "余额不足"；APIError → 透传错误；Exception → 兜底"暂不可用"。每个都有对应的用户友好文案，**不暴露技术细节给前端**。

**Q2：AVAILABLE_TOOLS 怎么注册给模型的？模型怎么知道每个工具的参数？**
A：通过 OpenAI Tool Calling 协议——把 tools 数组传到 `chat.completions.create(tools=...)`，每个工具是 `{type: "function", function: {name, description, parameters}}`。`parameters` 是 JSON Schema，模型按 schema 解析用户意图后返回 `tool_calls`。

**Q3：上下文超长（项目 1000 个任务）怎么办？现在的截断策略合理吗？**
A：当前 `build_project_context` 内部用 `add_section` 控制总长度（按字符数估算 token，超阈值丢尾部 section）。1000 个任务时，"任务统计"按状态分桶，不会按条列；只列关键词命中的前 N 个任务标题。合理性的边界：项目超 5000 任务且关键词命中很多时，会截断，但兜底是模型仍能回答统计性问题（"项目里多少未完成任务"）。

**Q4：流式响应客户端中途断开，后端写库会有空记录吗？**
A：当前流式接口（`AIStreamChatView`）**没有**写 AIMessage——流式生成结束后才能拿到完整 content。客户端断开会导致生成器迭代抛 `BrokenPipeError`，没有空记录。代价是流式问答不持久化（默认不存）。

**Q5：工具调用 3 轮后还没收敛会怎样？**
A：循环退出，返回"已超过工具调用上限"字符串给用户。3 轮里至少能完成"读上下文 → 工具调用 → 总结"这一组合，超出说明 prompt 设计有问题或者请求本身太复杂（如"创建 10 个任务并跑测试"），应拆开。

**Q6：system prompt 强调 "ID 是 UUID" 是基于什么真实问题？**
A：DeepSeek 早期版本经常把任务/列 ID 当整数返回（如 `column_id: 1`），导致 ORM `get(id=1)` 报 ValidationError（UUID 字段不接受 int）。Prompt 约束 + 工具 description 双重强调后，错误率大幅下降。

**Q7：想加一个"自动生成迭代周报"工具，需要改哪几个文件？**
A：(1) `room/ai_utils.py` AVAILABLE_TOOLS 列表加一项；(2) `execute_tool` 大 if-elif 增加分支；(3) 实现函数（查 Sprint + Task + Comment 聚合）；(4) `system_prompt_full` 可选加一句"周报请用这个工具"。前端不用改，因为是同一个 chat 入口。

---

## 3. QA API 测试执行器深度拆解（新旧两套）

### 3.A 数据流 / 调用链

**新版 `ApiAutoTestExecutor`**（`backend/qa_center/api_auto_executor.py:180`）：

```
POST /api/qa/auto-execute/   {suite_id, environment_id?}
  └─ ApiAutoTestExecutor(suite_id, user, environment_id).execute()
      ├─ 拉 suite + active_cases.order_by('sort_order')
      ├─ resolve_project_environment(suite.project, env_id)
      ├─ load_project_globals(suite.project)
      ├─ build_variable_pool(env, global_vars)        # 三层优先级合并
      ├─ ApiAutoTestResult.objects.create(status='running')
      ├─ for case in active_cases:
      │     _execute_case(case)
      │     ├─ render_value(headers, vars)            # 渲染 headers
      │     ├─ resolve_url(case.url, vars)            # base_url 拼接
      │     ├─ render_string(case.body, vars)         # 渲染 body
      │     ├─ normalize_query_params(case.query_params, vars)
      │     ├─ build_file_tuples(case.form_files, vars)
      │     ├─ requests.request(method, url, headers, params, json/data, files, timeout=30)
      │     ├─ 解析响应 → response_data + response_headers + status_code
      │     ├─ ResponseContext.from_raw(...) → run_assertions(active_assertions, ctx)
      │     ├─ expected_status 兜底（无 status_code 断言时）
      │     └─ ApiAutoTestCaseResult.objects.create(...)
      ├─ 汇总 passed / failed / error → 更新 ApiAutoTestResult.status
      └─ if final_status in (failed, error):
            for fr in failed_results: create_bug_from_test_failure(case, result, error)
```

**旧版 `execute_api_test_case`**（`backend/qa_center/test_executor.py:172`）：

仍被 `views_api_test.ApiTestCaseBatchRunView` 和 `views_devops.execute_api_test_cases` 引用。差异：
- 直接走 `requests`（曾经是 `django.test.Client`，已演化）
- 没有变量池 / 模板引擎
- 断言协议不同：`expected_response.assertions` 数组（type/field/operator/expected_value/value）
- 结果**双写** `ApiTestResult` + `TestResult`（DevOps 大盘要看 TestResult）

### 3.B 关键代码片段

**变量池三层优先级** `backend/qa_center/template_engine.py:29`：

```python
def build_variable_pool(*, environment=None, global_vars=None, overrides=None):
    pool = {}
    # 优先级：globals (低) < environment (中) < overrides (高)
    for v in global_vars or []:
        pool[v.name] = v.value
    if environment:
        for k, v in (environment.variables or {}).items():
            pool[k] = v
    if overrides:
        pool.update(overrides)
    return pool
```

**`{{var}}` 替换 + 找不到保留原样** `backend/qa_center/template_engine.py:79`：

```python
_PLACEHOLDER_RE = re.compile(r'\{\{\s*([\w\.]+)\s*\}\}')

def render_string(text: str, variables: dict) -> str:
    if not text or not isinstance(text, str):
        return text
    def replace(m):
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        return m.group(0)            # 保留 {{var}} 原样，方便定位漏配
    return _PLACEHOLDER_RE.sub(replace, text)
```

**base_url 拼接** `backend/qa_center/template_engine.py:103`：

```python
def resolve_url(url: str, variables: dict) -> str:
    rendered = render_string(url, variables)
    if rendered.startswith(('http://', 'https://')):
        return rendered                            # 绝对 URL 直接用
    base_url = variables.get('base_url') or variables.get('host') or ''
    if base_url and not rendered.startswith('/'):
        return base_url.rstrip('/') + '/' + rendered
    return base_url.rstrip('/') + rendered if base_url else rendered
```

**单用例执行** `backend/qa_center/api_auto_executor.py:263`：

```python
def _execute_case(self, case):
    headers = case.headers or {}
    if case.content_type:
        headers['Content-Type'] = case.content_type

    url = te.resolve_url(case.url, self._variables)
    headers = te.render_value(dict(headers), self._variables)
    raw_body = te.render_string(case.body or '', self._variables)
    params = rb.normalize_query_params(case.query_params, self._variables)
    files = rb.build_file_tuples(case.form_files, self._variables)

    body = None
    if raw_body and case.method in ['POST', 'PUT', 'PATCH']:
        body = json.loads(raw_body) if case.content_type == 'application/json' else raw_body

    if files:    # multipart 上传：去掉硬编码 Content-Type
        headers = {k: v for k, v in headers.items() if k.lower() != 'content-type'}

    response = requests.request(
        method=case.method, url=url, headers=headers, params=params,
        json=body if isinstance(body, dict) and not files else None,
        data=body if (isinstance(body, str) or (isinstance(body, dict) and files)) else None,
        files=files, timeout=30,                # ⚠️ 写死 30s
    )
    # ... 断言 + 写库
```

**统一断言入口** `backend/qa_center/unified_assertions.py:_smart_eq` 关键逻辑：

```python
def _smart_eq(a, b):
    """智能等值：'30' == 30 通过；True == 1 不通过。"""
    if isinstance(a, bool) or isinstance(b, bool):     # bool 优先单独判
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, str):
        try: return a == type(a)(b)
        except: return False
    if isinstance(b, (int, float)) and isinstance(a, str):
        try: return b == type(b)(a)
        except: return False
    return a == b
```

**失败自动建 Bug** `backend/qa_center/bug_utils.py:21`：

```python
def create_bug_from_test_failure(case, test_result, error_message=''):
    project_id = case.project_id if hasattr(case, 'project_id') else case.suite.project_id
    source_test_type = 'api_auto'
    # 推断 source_test_type（通过类名）
    if 'Performance' in type(test_result).__name__: source_test_type = 'performance'
    if 'Ui' in type(case).__name__: source_test_type = 'ui_auto'

    if _existing_open_bug(project_id, source_test_type, case.id):
        return None                                  # 同源未关闭 Bug 不重复建

    Bug.objects.create(
        project_id=project_id,
        title=f'[自动] {case.name} 执行失败',
        description=error_message,
        priority='medium',
        source_test_type=source_test_type,
        source_case_id=case.id,
    )
```

### 3.C 设计权衡 / 易混点

| 决策 | 为什么 | 坑 |
|---|---|---|
| 新旧执行器并存 | 旧版被 DevOps + 旧用例引用，没下线；新版支持外部 URL + 变量 + 断言抽象 | 维护两份代码、断言协议不同 |
| `timeout=30` 写死 | 当前实现忽略 `case.timeout_seconds`（run_plan_executor 那边用了） | 慢接口会被强制 30s 切断 |
| 自动建 Bug 去重 | 按 `(project, source_test_type, source_case_id)` 找未关闭 Bug | 关闭后再次失败会再建（这是有意的：回归暴露问题） |
| 断言走 `ResponseContext` 抽象 | 新旧两套共用同一套断言引擎 | 旧协议（field/operator）映射到新协议有少量字段冗余 |
| `_smart_eq` 隔离 bool | Python 里 `True == 1` 成立，但业务上"状态码 200 vs True"绝不应该 pass | 字段是 bool 时需要显式写 true/false |
| `{{var}}` 找不到保留原样 | 方便排查漏配——日志里能看到 `{{token}}` 没被替换 | 用户偶尔会拿到带占位符的请求，从响应错误才发现 |
| 变量池三层优先级与 Postman 对齐 | 降低学习成本 | 上游 case 提取的变量塞 overrides，但跨 suite 不传递（**已知限制**） |
| `headers = case.headers` 不 copy | 性能小优化 | 多 case 共享 headers dict 时 mutate 可能串（潜在 bug） |

### 3.D 问答库

**Q1：suite 里 case A 登录拿 token，case B 怎么用？**
A：(1) case A 配置 `extractors`，`json_path="$.data.token"`, `variable_name="token"`；(2) 执行 case A 后 executor 把 `token=xxx` 塞进 `self._variables`；(3) case B 在 headers 写 `{"Authorization": "Bearer {{token}}"}`，render_value 自动替换。链路：`extractor → _variables → render_value`。

**Q2：case A 网络超时，case B 还会执行吗？怎么改成"前置失败就跳过"？**
A：当前会继续。`_execute_case` 抛异常被 catch 在内部，循环不会 break。要改成短路，可以加 `case.fail_fast` 字段，在循环里检查上一个 case_result.passed，如果为 False 且 fail_fast=True 就 break 并标记后续为 skipped。

**Q3：同一 case 失败 100 次会建 100 个 Bug 吗？**
A：不会。`_existing_open_bug(project_id, source_test_type, source_case_id)` 用三元组查未关闭的 Bug，存在就跳过。前提是上一个 Bug 没被人手动关闭。

**Q4：旧版执行器为什么不能打 https://api.example.com/v1/users？**
A：实际上当前代码也用 `requests`，所以能打。文件头注释里"用 django.test.Client"是早期事实，已演化但保留了双写 TestResult 的特性。**建议措辞调整为：旧版断言协议老，没变量池，没 base_url 拼接**。

**Q5：JSON 响应 `{"data": {"items": [{"id": 1}]}}`，怎么写断言提取 id？**
A：断言 type=`json_equals`, json_path=`$.data.items[0].id`, expected_value=`1`（或字符串 `"1"`，靠 `_smart_eq` 容错）。提取：extractor 配 json_path=`$.data.items[0].id`, variable_name=`user_id`，下游 case 用 `{{user_id}}` 引用。

**Q6：`headers = case.headers` 不 copy 有什么风险？**
A：headers 是 dict（来自 JSONField），如果用户在多个 case 共享同一份配置（Django ORM 不会自动深拷贝 JSONField），`headers['Content-Type'] = ...` 会写回**模型实例**的 dict，跨 case 污染。这是潜在 bug，应该 `headers = dict(case.headers or {})`。

**Q7：新版断言里 status_code 兜底什么时候触发？**
A：见 `api_auto_executor.py:333`。如果 active_assertions 里没有 `assertion_type='status_code'` 的，但 case.expected_status 有值（如 200），就在 assertion_details 头部插一条状态码断言，避免"忘配断言导致 500 也算 pass"。

---

## 4. UI 测试深度拆解（Playwright 录制 / 回放）

### 4.A 数据流 / 调用链

这一章最复杂，核心模式是：**Django 主进程 → 子进程（Playwright）→ stdin/stdout JSON Lines → WebSocket 推前端**。

**录制流程**：

```
前端 RecorderPanel
  └─ 建 ws → /ws/qa/recorder/                            (RecorderConsumer)
      └─ 发 {type: "start", url: "https://..."}
          └─ RecorderConsumer 起 RecorderSession
              └─ subprocess.Popen([python, -m, qa_center.workers.recorder_worker])
                  ├─ 子进程 Playwright launch chromium (headless=False)
                  ├─ context.add_init_script(RECORDING_SCRIPT)       # 注入 JS
                  ├─ page.expose_binding("onRecordEvent", on_record_event)
                  ├─ page.goto(url)
                  └─ 用户在浏览器点 → JS 调 window.onRecordEvent({...})
                      └─ Python 收到 → emit JSON 到 stdout
                          └─ 主进程读 stdout → _map_event → WS push 前端
                              └─ 前端实时画步骤列表
```

**回放流程**：

```
前端 → POST /api/qa/ui-cases/{id}/run/   → 返 {task_id}
                                              ↓
                                  RunnerSupervisor.execute_ui_case
                                  ├─ subprocess.Popen([python, -m, qa_center.workers.runner_worker])
                                  ├─ stdin.write(case_data_json + '\n')
                                  ├─ register_runner(task_id, proc)         # 全局 _RUNNERS 表
                                  ├─ watchdog Timer(300s) → terminate
                                  ├─ stderr drain 线程
                                  ├─ for line in stdout:
                                  │     event = json.loads(line)
                                  │     on_event(event)                    # 转 WS
                                  │     if DEBUG: write to io_log
                                  │     if type == 'finished': final_result = event
                                  └─ unregister_runner
前端 ws /ws/qa/run/{task_id}/    ← group_send ui_run_{task_id}  ←  on_event
```

**中止**：

```
前端 → POST /api/qa/ui-cases/{run}/abort/
      └─ abort_runner(task_id)
          └─ _RUNNERS[task_id].terminate()
              └─ 子进程退出 → stdout 结束 → 主循环跳出
```

### 4.B 关键代码片段

**子进程注册表** `backend/qa_center/workers/runner_supervisor.py:19`：

```python
_RUNNERS: dict[str, "subprocess.Popen"] = {}
_RUNNERS_LOCK = threading.Lock()
_EVENTS: dict[str, list[dict]] = {}             # 历史事件回放缓存
_EVENTS_TTL = 60.0

def register_runner(task_id, proc):
    with _RUNNERS_LOCK: _RUNNERS[task_id] = proc

def abort_runner(task_id):
    with _RUNNERS_LOCK: proc = _RUNNERS.get(task_id)
    if proc is None: return False
    if proc.poll() is None: proc.terminate()
    return True
```

**execute_ui_case 完整流程** `backend/qa_center/workers/runner_supervisor.py:104`：

```python
def execute_ui_case(case_data, on_event, timeout_seconds=300, task_id=None):
    proc = subprocess.Popen(
        [sys.executable, "-m", "qa_center.workers.runner_worker"],
        cwd=backend_dir,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", bufsize=1,
    )
    task_id = task_id or uuid.uuid4().hex
    register_runner(task_id, proc)

    # DEBUG 模式落盘所有事件
    if os.environ.get("UI_TEST_DEBUG", "").lower() in ("1", "true", "yes"):
        io_log = open(f".playwright-temp/io_{task_id}.log", "w")

    on_event({"type": "supervisor_meta", "task_id": task_id, "worker_pid": proc.pid})

    proc.stdin.write(json.dumps(case_data) + "\n")
    proc.stdin.flush()
    proc.stdin.close()

    # stderr drain 线程，避免管道满阻塞
    threading.Thread(target=lambda: [stderr_buf.append(l) for l in proc.stderr], daemon=True).start()

    # 超时 watchdog
    watchdog = threading.Timer(timeout_seconds, lambda: proc.terminate())
    watchdog.start()

    final_result = {"type": "finished", "success": False}
    for line in proc.stdout:
        event = json.loads(line.strip())
        on_event(event)
        if event.get("type") == "finished":
            final_result = event

    watchdog.cancel()
    proc.wait(timeout=10)
    unregister_runner(task_id)
    return final_result
```

**事件名映射（向后兼容）** `backend/qa_center/consumers.py:131`：

```python
def _map_event(event_type: str) -> str:
    """worker 内部事件名 → 前端约定的事件名"""
    return {
        "click": "record_event",
        "fill": "record_event",
        "assert": "record_assert_event",
        "step_done": "step_run_done",
    }.get(event_type, event_type)
```

**注入 JS 的稳定 selector 算法**（节选自 `recorder_worker.py:72` RECORDING_SCRIPT）：

```javascript
function isStableId(id) {
    // 过滤 Element Plus 的临时 ID：el-id-12345-67890
    if (/^el-id-\d+-\d+$/.test(id)) return false;
    if (/^[a-z0-9]{8,}$/.test(id) && !id.includes('-')) return false;  // hash 类
    return true;
}

function isStableClass(cls) {
    if (/^is-/.test(cls)) return false;      // is-active / is-disabled 状态类
    if (/^el-id-/.test(cls)) return false;
    if (/^css-[a-z0-9]{6,}$/.test(cls)) return false;  // CSS-in-JS hash
    return true;
}

function buildSelector(el) {
    // 优先级：id > data-testid > role+name > text > class chain > nth-child
    if (el.id && isStableId(el.id)) return `#${el.id}`;
    const testid = el.getAttribute('data-testid');
    if (testid) return `[data-testid="${testid}"]`;
    // ...
}
```

**el-select 录制特殊处理**（节选自 `recorder_worker.py:499`）：

```javascript
// Element Plus 的 el-select 下拉项 teleport 到 body 下
// 点击下拉项时，wrapper 已经不在 DOM 树正常位置，selector 算法失效
// 解决：mousedown 时记下打开的 el-select wrapper
let lastSelectWrapper = null;
document.addEventListener('mousedown', (e) => {
    const sw = e.target.closest('.el-select');
    if (sw) lastSelectWrapper = buildSelector(sw);
}, true);

document.addEventListener('click', (e) => {
    const item = e.target.closest('.el-select-dropdown__item');
    if (item && lastSelectWrapper) {
        // 还原成 "先点 wrapper 打开下拉，再 contains-text 选项" 两步
        emit({type: 'click', selector: lastSelectWrapper});
        emit({type: 'click', selector: `.el-select-dropdown__item:has-text("${item.innerText}")`});
        return;
    }
});
```

### 4.C 设计权衡 / 易混点

| 决策 | 为什么 | 坑 / 副作用 |
|---|---|---|
| 子进程而非协程 | Playwright 同步 API 与 asyncio 冲突 | 进程启动有 ~500ms 开销 |
| stdin/stdout JSON Lines | 1:1 进程间通信，无依赖 | 大事件（如截图 base64）会撑大 stdout 缓冲 |
| `_EVENTS` 60s 回放 | 前端 WS 连上时可能错过启动期事件，回放兜底 | 用户切到其他页面 60s 内回来还能补；超时则丢 |
| `_RUNNERS` 全局表 + Lock | abort 端点要精确终结指定进程 | 多 Django 进程部署时全局表不共享（已知限制） |
| watchdog Timer 5min | 防死循环 | 真正慢的用例（如 5 分钟登录流程）会被误杀 |
| stderr drain 独立线程 | stderr 管道满会让 worker 阻塞 | 多了一个线程，进程退出时要 join |
| `UI_TEST_DEBUG` 环境变量 | 开发期能看到所有事件流（落盘到 `.playwright-temp/io_<id>.log`） | 生产环境记得关，否则磁盘爆 |
| 过滤 `el-id-*` 类 | Element Plus 的临时 ID 每次刷新都变，录制 selector 会失效 | 极端场景（自定义组件有合法 `el-id-xxx`）会过滤错 |
| el-select 走 wrapper + has-text | 下拉项 teleport 到 body，原 selector 路径丢失 | 选项文本变了 selector 就失效 |
| input wrapper click 不录、等 change 录 fill | 避免 "点击 input + fill" 双步 | 极少数原生 input click（如颜色选择器）会丢录 |

### 4.D 问答库

**Q1：用户点击 el-select 的下拉项，事件怎么从 Chromium 到前端步骤列表？**
A：完整时序：
1. 用户在 Chromium 里点下拉项 → DOM click 事件
2. 注入的 RECORDING_SCRIPT 监听器触发 → 识别为 dropdown item → 拆成两步 emit
3. `window.onRecordEvent({type:'click', selector:'.el-select'})` 调用（这是 expose_binding 暴露的 Python 函数）
4. recorder_worker.py 收到 → emit JSON 到 stdout
5. RecorderConsumer 通过 RecorderSession 读 stdout → _map_event 改成 `record_event`
6. self.send_json(...) 推前端 ws
7. 前端 RecorderPanel 监听器追加到 steps 数组 → Vue 渲染

**Q2：录制时为什么要过滤 `el-id-12345`？不过滤会怎样？**
A：Element Plus 的 `:id` 是 `v4()` 生成的临时值，每次 mount 都不同。如果不过滤，录制出 `#el-id-12345-67890` 的 selector，回放时这个 ID 已经变了，定位失败。过滤后退到下一优先级（data-testid / role / class chain）。

**Q3：worker 进程 segfault，主进程怎么知道？前端会收到什么？**
A：stdout 关闭 → 主循环 `for line in proc.stdout` 退出。`proc.wait()` 返回非 0 退出码。代码里有兜底（`runner_supervisor.py:245`）：如果 returncode 不是 0/None 且没拿到 `finished` 事件，emit 一条 `{type:'error', code:'WORKER_CRASHED'}` 给前端，附最近 20 行 stderr。

**Q4：5 个项目同时录制，进程会串吗？**
A：不会。每个录制会话起独立子进程 + 独立 `recorder_{channel_name}` group。channel_name 是 Channels 给每个 WebSocket 连接生成的全局唯一 ID，所以即使同一用户多标签也不会串。但 5 个 Chromium 会消耗 ~5GB 内存，单机有上限。

**Q5：stdin 为什么用 JSON Lines 而不是 protobuf？**
A：(1) 调试方便——`io_log` 落盘是人类可读的；(2) 无额外依赖；(3) 事件量级（每秒 < 10 条）不需要二进制效率。protobuf 强项是高频小消息或多语言，这里都不沾。

**Q6：中止录制时 Chromium 没关干净，会留下什么进程？**
A：`proc.terminate()` 发 SIGTERM 到 worker，worker 应该捕获并优雅关 browser。但如果 worker 卡在 Playwright 内部（如等待网络），SIGTERM 可能不响应；watchdog 后续会 SIGKILL，但 Chromium 子进程**不会**被信号传播——这就是 .playwright-temp 启动时清理逻辑的来源（每次启动扫一下孤儿 Chromium 进程）。

**Q7：单步试运行 `_do_run_step` 复用了 runner_worker 的什么？**
A：复用了步骤执行函数（点击/填值/断言 dispatch），但不复用整个 main 循环。`_do_run_step` 接一条 step + 当前 page 上下文，执行一步并发 step_run_done 事件回去。这样录制过程中能"边录边试"，不用从头跑。

---

## 5. 性能测试深度拆解（Locust headless）

### 5.A 数据流 / 调用链

```
前端 PerformanceTestPanel
  └─ POST /api/qa/performance-cases/{id}/start/  {users, spawn_rate, run_time}
      └─ PerformanceTestCaseViewSet.start
          └─ LocustRunner.start_test(test_case, callback)
              ├─ generate_locustfile(test_case, metrics_file)
              │   └─ 拼出 Python 代码 → 写 tmp/syncboard-locust/locustfile_current.py
              │       └─ 内含 @events.test_start / test_stop / request.add_listener
              ├─ subprocess.Popen(["locust", "-f", file, "--headless",
              │                    "-u", users, "-r", rate, "--run-time", time])
              ├─ _monitor_process 线程启动
              │   └─ while proc 存活:
              │         读 metrics_file (JSON)
              │         _notify_callbacks(metrics)   ← 每 0.5s
              │         sleep(0.5)
              └─ _locust_runners[case_id] = self     # 全局表

   ↕ 0.5s 一次
metrics_file (JSON)  ← Locust 子进程通过 request listener 持续写入

callback → views_performance._send_ws_update
  └─ async_to_sync(channel_layer.group_send)("performance_test_{id}", {...})
      └─ PerformanceTestConsumer.test_update → ws.send → 前端 ECharts
```

### 5.B 关键代码片段

**TestMetrics dataclass** `backend/qa_center/locust_runner.py:19`：

```python
@dataclass
class TestMetrics:
    state: str = "idle"                  # idle / running / stopped
    start_time: float = 0
    total_requests: int = 0
    failed_requests: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=10000))
    p50: float = 0
    p90: float = 0
    p95: float = 0
    p99: float = 0
    throughput: float = 0                # req/s
    error_rate: float = 0
```

**动态生成 locustfile** `backend/qa_center/locust_runner.py:71`：

```python
def generate_locustfile(test_case, metrics_file):
    code = f'''
import json, time
from locust import HttpUser, task, events
from collections import deque

_metrics_data = {{
    "state": "idle",
    "total_requests": 0,
    "failed_requests": 0,
    "response_times": deque(maxlen=10000),
}}

def write_metrics():
    rt = sorted(_metrics_data["response_times"])
    n = len(rt)
    p = lambda q: rt[int(n*q)] if n else 0
    with open(r"{metrics_file}", "w") as f:
        json.dump({{
            "state": _metrics_data["state"],
            "total_requests": _metrics_data["total_requests"],
            "failed_requests": _metrics_data["failed_requests"],
            "p50": p(0.5), "p90": p(0.9), "p95": p(0.95), "p99": p(0.99),
        }}, f)

@events.test_start.add_listener
def on_start(**kw):
    _metrics_data["state"] = "running"
    write_metrics()

@events.test_stop.add_listener
def on_stop(**kw):
    _metrics_data["state"] = "stopped"
    write_metrics()

@events.request.add_listener
def on_request(request_type, name, response_time, exception, **kw):
    _metrics_data["total_requests"] += 1
    if exception: _metrics_data["failed_requests"] += 1
    _metrics_data["response_times"].append(response_time)
    if _metrics_data["total_requests"] % 10 == 0:
        write_metrics()

class TestUser(HttpUser):
    host = "{test_case.host}"
    @task
    def do_request(self):
        self.client.{test_case.method.lower()}("{test_case.path}",
            headers={json.dumps(test_case.headers)},
            json={json.dumps(test_case.body) if test_case.body else 'None'})
'''
    with open(LOCUSTFILE_PATH, "w") as f: f.write(code)
```

**monitor 线程** `backend/qa_center/locust_runner.py:238`：

```python
def _monitor_process(self):
    while self.proc and self.proc.poll() is None:
        try:
            with open(self.metrics_file) as f:
                data = json.load(f)
            self.metrics = TestMetrics(**data)
            self._notify_callbacks(self.metrics)
        except (FileNotFoundError, json.JSONDecodeError):
            pass                          # 还没写第一次 / 写一半被读
        time.sleep(0.5)
```

**WS 推送** `backend/qa_center/views_performance.py:65`：

```python
def _send_ws_update(case_id, metrics):
    async_to_sync(channel_layer.group_send)(
        f"performance_test_{case_id}",
        {"type": "test_update", "data": asdict(metrics)}
    )
```

### 5.C 设计权衡 / 易混点

| 决策 | 为什么 | 副作用 |
|---|---|---|
| 文件 IPC 不用 Redis | Locust 子进程是独立 Python 解释器，引 Redis 客户端要写新依赖；本地文件简单 | 跨机器部署时只能用 NFS（强限制） |
| 固定文件名 `locustfile_current.py` | 避免临时文件爆炸 | **同时只能跑一个性能测试用例**（已知限制） |
| response_times deque maxlen=10000 | 防内存爆炸（1000 req/s × 600s = 6×10⁵） | 高 N 时 p99 不准（截断了） |
| percentile 用 `sorted()` 取索引 | 简单，N 小（≤10000）够用 | O(N log N) 每次都排，更佳是 t-digest |
| monitor 0.5s 一次 | ECharts 2 Hz 刷新够看，不压垮 channel layer | 末尾 1~2s 数据可能没采到 |
| 主进程读 + 子进程写同一文件 | 简单 | 偶发 read 到半写 JSON → `JSONDecodeError` → except 跳过等下一秒 |
| `_locust_runners` 类变量 | 全局拿 runner 实例方便 stop / 查状态 | 多 Django 进程部署时不共享（已知限制） |
| 每 10 次 request 才 write_metrics | 高并发下避免 1000 次/s 写盘 | 末尾 < 10 次 request 不刷新（test_stop 兜底刷一次） |

### 5.D 问答库

**Q1：同时跑两个性能测试会怎样？**
A：当前实现会**互相覆盖**。固定文件名 `locustfile_current.py` 会被第二次写覆盖；`_locust_runners[case_id]` 用 case_id 区分但 metrics_file 也是固定路径。要支持并发，改成 `locustfile_{case_id}.py` + `metrics_{case_id}.json`，再加一个进程数上限（避免内存爆）。

**Q2：p99 怎么算的？大数据量下的性能问题？**
A：`sorted(response_times)[int(n*0.99)]`，O(N log N) 每次都排。N=10000 时一次排约几毫秒，每 10 次 request 排一次 = 还能接受；N=100k 会卡。优化：增量算法（t-digest / HDR Histogram），或仅在 write_metrics 时排。

**Q3：主进程读时子进程在写，会读到半个 JSON 吗？**
A：会，特别是 100k req/s 高并发。所以 monitor 线程里 `try: json.load(f) except JSONDecodeError: pass`，下一秒（0.5s）再读。正确性影响小（图表少一个采样点），但**没用文件锁**——这是有意妥协换简单。生产级方案要用 fcntl.flock 或 tempfile + atomic rename。

**Q4：`--run-time 60s` 之后子进程退出，主进程怎么知道？**
A：`_monitor_process` 循环条件是 `self.proc.poll() is None`，Locust 主动退出后 poll 返回 returncode，循环退出。test_stop hook 在退出前会把 state='stopped' 写进 metrics_file，最后一次读到这个状态。

**Q5：前端断开 WS，性能测试还跑完吗？指标会丢吗？**
A：跑完——Locust 子进程独立运行，与 WS 解耦。指标也不丢——`metrics_file` 一直在写，前端重连后 NotificationConsumer.connect 时如果需要可以读 file 兜底（当前实现没做，只靠实时 group_send，**这是已知漏洞**）。

**Q6：想加 SLA 告警（p95 > 500ms 告警），改哪？**
A：在 `_notify_callbacks` 里判 `if metrics.p95 > threshold: send_alert(...)`。复杂方案：定义 `PerformanceTestThreshold` 模型，每个 case 配阈值，runner 加载阈值后在 monitor 线程里比较 → 触发 channel layer 推 alert 通道。

---

## 6. DevOps 平台深度拆解

### 6.A 数据流 / 调用链

DevOps 模块四块业务：

**1. Dashboard 大盘**：
```
GET /api/qa/devops/stats/?days=7
  └─ DashboardStatsView.get
      ├─ TestResult.objects.filter(...).aggregate()           → overview
      ├─ TestResult.objects.values('status').annotate(count)  → status_count
      ├─ TestResult.objects.values('test_type').annotate()    → by_type
      └─ 30 天循环 filter(created_at__date=...)               → daily_trend
```

**2. CI/CD 配置 CRUD**：
```
GET/POST/PATCH/DELETE /api/qa/devops/cicd-config/
  └─ CiCdIntegrationView → CiCdConfig 模型（name/ci_type/webhook_url/api_token/branch/auto_trigger）
```

**3. Pipeline 触发与 Webhook**：
```
触发（主动）：
POST /api/qa/devops/cicd-config/{id}/trigger/
  └─ PipelineRunTriggerView.post
      ├─ PipelineRun.objects.create(status='running')
      └─ threading.Thread(_simulate_run).start()    # ⚠️ 当前是 mock，不真调 Jenkins

回调（被动）：
POST /api/qa/devops/cicd-config/{id}/webhook/
  └─ PipelineRunWebhookView.post  (permission_classes=[])
      ├─ 校验 X-CI-Token header == config.api_token
      └─ PipelineRun.objects.create(...)  # 外部 CI 上报
```

**4. TestTask 编排**：
```
POST /api/qa/devops/tasks/{id}/execute/
  └─ TestTaskExecuteView.post
      ├─ task.status = 'running' + save()
      └─ threading.Thread(_execute_test_task).start()
          └─ _execute_test_task:
              ├─ 调 views_api_test.execute_api_test_cases(api_ids)
              ├─ 调 views_ui_test.execute_ui_test_cases(ui_ids)
              ├─ 没配 case 时 → _simulate_test_execution mock
              ├─ 写 TestResult
              ├─ 更新 task.last_result
              └─ _send_notification(level='success'|'test_failure')
                  ├─ async_to_sync(group_send)('system_broadcast', ...)
                  └─ bulk_create Notification（前 50 个活跃用户）
```

### 6.B 关键代码片段

**双写通知** `backend/qa_center/views_devops.py:30`：

```python
def _send_notification(title, message, level='info'):
    # 1. 实时 WS 推送
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'system_broadcast',
        {'type': 'system_message', 'data': {
            'title': title, 'message': message, 'level': level,
            'timestamp': timezone.now().isoformat(),
        }}
    )
    # 2. DB 持久化（活跃用户前 50 个）
    recent_users = User.objects.filter(is_active=True).order_by('-last_login')[:50]
    Notification.objects.bulk_create([
        Notification(user=u, title=title, message=message, level=level)
        for u in recent_users
    ])
```

**Dashboard 聚合** `backend/qa_center/views_devops.py:61`：

```python
class DashboardStatsView(APIView):
    def get(self, request):
        days = int(request.GET.get('days', 7))
        since = timezone.now() - timedelta(days=days)

        qs = TestResult.objects.filter(created_at__gte=since)
        overview = {
            'total': qs.count(),
            'passed': qs.filter(status='passed').count(),
            'failed': qs.filter(status='failed').count(),
            'pass_rate': ...,
        }
        by_type = list(qs.values('test_type').annotate(count=Count('id')))
        # 30 天趋势
        daily_trend = []
        for i in range(days):
            day = timezone.now().date() - timedelta(days=i)
            day_qs = TestResult.objects.filter(created_at__date=day)
            daily_trend.append({
                'date': day.isoformat(),
                'total': day_qs.count(),
                'passed': day_qs.filter(status='passed').count(),
            })
        return Response({'overview': overview, 'by_type': by_type, 'daily_trend': daily_trend})
```

**后台执行 TestTask** `backend/qa_center/views_devops.py:397`：

```python
def _execute_test_task(task_id):
    task = TestTask.objects.get(id=task_id)
    try:
        api_ids = task.api_case_ids or []
        ui_ids = task.ui_case_ids or []

        results = []
        if api_ids:
            results.extend(execute_api_test_cases(api_ids))   # 旧版执行器
        if ui_ids:
            results.extend(execute_ui_test_cases(ui_ids))

        if not (api_ids or ui_ids):
            results = _simulate_test_execution()              # mock

        passed = sum(1 for r in results if r.get('passed'))
        task.status = 'completed'
        task.last_result = {'passed': passed, 'total': len(results), 'details': results}
        task.save()

        level = 'success' if passed == len(results) else 'test_failure'
        _send_notification(f'测试任务 {task.name} 完成', f'通过 {passed}/{len(results)}', level)
    except Exception as e:
        task.status = 'failed'
        task.save()
        _send_notification(f'测试任务 {task.name} 失败', str(e), 'error')
```

**Webhook 公开端点** `backend/qa_center/views_devops.py:775`：

```python
class PipelineRunWebhookView(APIView):
    permission_classes = []        # ⚠️ 公开，靠 token 鉴权

    def post(self, request, config_id):
        config = get_object_or_404(CiCdConfig, id=config_id)
        token = request.headers.get('X-CI-Token') or request.data.get('token')
        if token != config.api_token:
            return Response({'error': 'invalid token'}, status=403)

        PipelineRun.objects.create(
            config=config,
            commit_sha=request.data.get('commit_sha'),
            branch=request.data.get('branch'),
            status=request.data.get('status', 'running'),
            ...
        )
        return Response({'ok': True})
```

### 6.C 设计权衡 / 易混点

| 决策 | 为什么 | 坑 |
|---|---|---|
| `threading.Thread(daemon=True)` 跑后台 | 避免引 Celery 任务定义、能在请求内拿 result_id | **Django 重启会丢任务**（daemon 线程立即死） |
| Pipeline 用 mock `_simulate_run` | 原计划接 Jenkins API，当前占位 | 答辩时要诚实说"Jenkins 集成是 TODO" |
| Webhook `permission_classes=[]` | 外部 CI 不带 session，靠 token | token 走 header 或 body 都接受 → 容易绕过审计；建议只 header |
| `_send_notification` 双写 | 实时 WS + DB 兜底（用户离线后能补看） | 50 用户硬编码、不分项目（不在该项目的人也收到） |
| `_execute_test_task` 引用 `views_api_test / views_ui_test` | 复用代码 | 模块循环依赖隐患（views_devops 引 views_api_test，views_api_test 又能引 views_devops 的工具？目前没成环但要注意） |
| Dashboard 30 天循环 filter | 写起来简单 | N+1 风险，30 天 × 多个 status 查询 = 数据量大时卡 |
| `bulk_create` 不带 `ignore_conflicts` | 无唯一索引冲突风险 | 如果加唯一约束（user+title+timestamp）就会炸 |
| 五维质量评分 | 综合可视化项目健康 | 每维数学公式都不通用，迁移项目要重写 |

### 6.D 问答库

**Q1：TestTask 用 threading 不用 Celery，会有什么问题？怎么改？**
A：(1) Django gunicorn/uvicorn 重启时 daemon 线程立即死，任务半截丢；(2) 不能水平扩展（多实例下任务在哪个进程运行不可控）。改 Celery：定义 `@shared_task def execute_test_task(task_id)`，TestTaskExecuteView.post 里 `execute_test_task.delay(task_id)` 拿 result_id 返回前端轮询。

**Q2：Webhook token 校验有什么漏洞？怎么加固？**
A：(1) token 可以走 body 也可以走 header → CSRF 防护不一致；(2) token 是明文 DB 存（虽然不在 API 返回），泄漏即沦陷；(3) 没有 IP allowlist；(4) 没有 timestamp + signature 防重放。加固：强制 header + HMAC 签名（body+timestamp+secret），可选 IP allowlist。

**Q3：Pipeline 怎么从 mock 切到真实 Jenkins？需改几处？**
A：`_simulate_run` 函数替换为真调 Jenkins API：`requests.post(f"{config.webhook_url}/job/{name}/build", auth=(user, token))`，拿 queueItem URL → poll 等 build number → 写 PipelineRun.external_id。中途 Jenkins 会回调我们的 webhook（已经支持），双向同步。共改 1 个函数（_simulate_run）+ 0 个新接口。

**Q4：五维质量评分里 "Bug 密度" 怎么算？**
A：见 quality-report 视图。Bug 密度 = `open_bugs / total_test_cases × 100`，其中 open_bugs = `Bug.objects.filter(project=p, status__in=['open','in_progress'])`，total_test_cases = `ApiTestCase + UiTestCase + ApiAutoTestCase`. 评分映射：0~5% → 90 分，5~10% → 75 分，10~20% → 60 分，> 20% → 40 分。

**Q5：TestTask 跑到一半 Django 重启怎么恢复？**
A：**目前不恢复**——task.status='running' 卡在那。重启后启动钩子可以扫一遍 `running` 状态超过 N 分钟的 task 标记为 `failed`（兜底），但正在跑的进度丢。彻底方案：换 Celery + result backend，重启后 Celery worker 继续干。

**Q6：`_send_notification` 给前 50 个活跃用户写记录，合理吗？**
A：不合理。问题：(1) 50 是硬编码 magic number；(2) "活跃用户" 按 last_login 排，不区分项目——外部用户也会收到内部项目通知；(3) 用户多了 50 不够，用户少时浪费。应该按 ProjectMember 关联只通知项目成员，或者全员（取决于消息类别）。

**Q7：Dashboard 接口在大数据量下没分页 / 没缓存，问题？**
A：30 天循环每次都 N 个 status 查询 = 几十次 DB query；TestResult 表 100w+ 行时一次接口几秒到十几秒。优化：(1) 用一次 `values('created_at__date', 'status').annotate(Count('id'))` GROUP BY 拿到所有数据 Python 端拆；(2) Redis 缓存 5min；(3) 按天物化视图（每天凌晨预计算）。

---

## 7. 跨模块全景：一次"AI 创建用例并执行"端到端走查

讲一个真实故事：**用户在 AIChat 输入"创建一个测试登录接口的 API 用例并立即运行"** → 走完六大模块。

### 7.1 时序图

```
浏览器                Django(REST+ASGI)         DB              DeepSeek           子进程/线程
   │                       │                    │                 │                    │
   │── POST /api/ai/chat/ ─▶                    │                 │                    │
   │                       ├─ build_project_context              │                    │
   │                       │   └─ ORM 多次查询 ──▶│                 │                    │
   │                       ◀── 返回上下文 ────────│                 │                    │
   │                       ├─ chat.completions.create(tools=) ───▶│                    │
   │                       ◀── tool_calls=[create_api_test_case]                       │
   │                       ├─ execute_tool('create_api_test_case', args)               │
   │                       │   └─ ApiTestCase.create() ────────▶│                    │
   │                       ◀── 返回 case_id      │                 │                    │
   │                       ├─ chat.completions.create(tools=) (第二轮) ───────────────▶│
   │                       ◀── tool_calls=[run_api_test_case]                          │
   │                       ├─ execute_tool('run_api_test_case', {case_id})             │
   │                       │   └─ execute_api_test_case(case)                          │
   │                       │       ├─ requests.post(login_url)                         │
   │                       │       ├─ 写 ApiTestResult ───────▶│                    │
   │                       │       └─ 写 TestResult ──────────▶│                    │
   │                       │           └─ (DevOps 大盘下次读 stats 会带上)              │
   │                       ◀── tool result {passed: true}                              │
   │                       ├─ chat.completions.create() (第三轮) ─────────────────────▶│
   │                       ◀── content="已创建并跑通登录用例 #123"                       │
   │                       ├─ AIMessage.objects.create() ────▶│                    │
   │                       │                                  │                       │
   │                       ├─ if test failed → _send_notification ─────────────────────│ (在线程内)
   │                       │   ├─ group_send('system_broadcast') ▶ NotificationConsumer
   │                       │   └─ bulk_create Notification ──▶│
   │ ◀── ws push (toast) ──┤                                                          │
   │ ◀── {answer:"..."} ───┤                                                          │
```

### 7.2 涉及的文件 / 模型 / WS

| 步骤 | 涉及文件 | DB 表 | WebSocket |
|---|---|---|---|
| 1. AIChat 提交 | `frontend/src/views/AIChat.vue` | - | - |
| 2. AIChatView 接收 | `backend/room/views/ai.py:50` | - | - |
| 3. build_project_context | `backend/room/ai_utils.py:75` | Project / Task / Column / TestResult | - |
| 4. DeepSeek tool_calls | `backend/room/views/ai.py:137` | - | - |
| 5. create_api_test_case 工具 | `backend/room/ai_utils.py:617`（execute_tool） | ApiTestCase | - |
| 6. run_api_test_case 工具 | 同上 → execute_api_test_case | ApiTestResult + TestResult | - |
| 7. （失败时）_send_notification | `backend/qa_center/views_devops.py:30` | Notification | `/ws/global/` |
| 8. 前端 toast | `frontend/src/stores/notification.ts` | - | NotificationConsumer |
| 9. AI 总结写库 | `backend/room/views/ai.py` | AIMessage | - |
| 10. 前端渲染回复 | `frontend/src/views/AIChat.vue` | - | - |

### 7.3 这条路径展示了什么

- **AI 域**：tool_calls 把"自然语言"翻译成"API 调用"，3 轮循环兜底
- **QA 执行器（旧版）**：execute_tool 调的是 `test_executor.py`（旧版），写 ApiTestResult + TestResult 双表
- **DevOps 大盘**：TestResult 表自动被 Dashboard 聚合，下次刷新 stats 接口能看到这次执行
- **WebSocket 实时层**：失败时通过 `system_broadcast` 推 toast，所有在线用户能感知
- **Notification 持久化**：bulk_create 保证用户离线后还能补看

### 7.4 极端情况

- **第一轮工具调用失败（ApiTestCase 创建失败）**：execute_tool 返回 `{error: "..."}` 给模型，模型在第二轮可能选择道歉而不是继续 run
- **第二轮 run_api_test_case 失败（接口 500）**：写 ApiTestResult.passed=False + 触发 `create_bug_from_test_failure`（新版执行器才有；旧版没有这个钩子）→ Bug 表多一条 → 看板可以展示
- **第三轮 AI 拒绝总结（DeepSeek 超时）**：兜底返回 "AI 服务暂时不可用"，但前两轮的写库已经持久化，不会回滚

---

## 附录 A：UUID vs 自增 ID 表

| 模型 | PK 类型 | 为什么 |
|---|---|---|
| **room app** | | |
| Project | UUID | 项目 ID 会出现在 URL（`/projects/{uuid}/board`），不暴露规模 |
| Column | UUID | 同 Project，前端用 UUID 操作列 |
| Task | UUID | 同 Column |
| TaskComment / TaskAttachment / TaskActivityLog | AutoField | 子资源，不暴露在 URL 顶层 |
| Notification | AutoField | 内部表 |
| AIConversation / AIMessage | AutoField | 内部表 |
| Sprint / SprintTask | AutoField | - |
| ProjectMember / ProjectRole | AutoField | - |
| **qa_center app** | | |
| ApiTestCase / ApiTestResult | AutoField | 早期设计未用 UUID，沿用 |
| ApiAutoTestSuite / Case / Assertion / Extractor / Result | AutoField | 同上 |
| UiTestCase / UiTestResult | AutoField | 同上 |
| TestEnvironment / TestGlobalVar | AutoField | - |
| TestResult（统一表） | AutoField | - |
| TestTask / CiCdConfig / PipelineRun | AutoField | - |
| Bug | AutoField | - |
| **system app** | | |
| User (Django auth) | AutoField | Django 默认 |
| Menu / Role / Permission | AutoField | - |

**为什么 AI 工具反复强调 UUID**：因为 room 的核心 3 个模型（Project/Column/Task）都是 UUID，而 DeepSeek 早期版本经常把 UUID 当成整数返回（`column_id: 1`），导致工具调用失败。

---

## 附录 B：WebSocket 路径 / 群组 / 协议总表

| 路径 | Consumer | Group 名 | 鉴权 | 主要消息协议 |
|---|---|---|---|---|
| `/ws/board/<project_id>/` | BoardConsumer | `board_{project_id}` | 项目成员（close 4003） | `{action, data}` — server 推 `{type: 'board_update', data: 'refresh'}` |
| `/ws/chat/<project_id>/` | ChatConsumer | `chat_{project_id}` | 项目成员 | `{message, user}` — Redis Stream 持久化 + 重连历史回放 |
| `/ws/global/` | GlobalConsumer | `system_broadcast` + `user_{id}` | 已认证 | `{type: 'system_message', level, message, title}` |
| `/ws/qa/dashboard/` | QAConsumer | `qa_dashboard` | 已认证 | `test_start` / `test_update` / `run_plan_progress` |
| `/ws/qa/recorder/` | RecorderConsumer | `recorder_{channel_name}` | 已认证（私有 group） | `start` / `stop` / `pause` / `resume` / `run_step` → server `record_event` / `record_assert_event` / `step_run_done` |
| `/ws/qa/performance/<id>/` | PerformanceTestConsumer | `performance_test_{id}` | 已认证 | `test_update` — TestMetrics dataclass 序列化 |
| `/ws/qa/test-run/<run_id>/` | TestRunProgressConsumer | `test_run_{run_id}` | 已认证 | `case_done` / `run_finished` |
| `/ws/qa/run/<task_id>/` | UiRunConsumer | `ui_run_{task_id}` | 已认证 | `run_event` — UI 用例执行进度（含 supervisor_meta / error / finished） |

**鉴权统一做法**：在 consumer.connect() 里读 `self.scope['user']`（由 AuthMiddlewareStack 注入），若 anonymous 或非项目成员则 `await self.close(code=4003)`。

**group_send 触发点**：
- 看板拖任务 → views_board.py
- 通知广播 → views_devops.py:30 `_send_notification`
- 性能指标 → views_performance.py:65 `_send_ws_update`
- UI 运行进度 → runner_supervisor.on_event 回调

---

## 附录 C：六大模块的"必读 6 文件"

按重要度排序，读完这 6 个文件就能把项目核心讲明白：

1. **`backend/room/ai_utils.py`**（924 行）— AI 域全貌：SYSTEM_PROMPT、build_project_context、AVAILABLE_TOOLS、execute_tool 大 if-elif、get_rag_answer 异常分级、get_streaming_answer 生成器
2. **`backend/qa_center/api_auto_executor.py`**（375 行）— 新版 API 执行器：变量池、模板渲染、断言抽象、自动 Bug 创建
3. **`backend/qa_center/workers/recorder_worker.py`**（770 行）— UI 录制核心：注入 JS 稳定 selector、el-select 特殊处理、Playwright 子进程入口
4. **`backend/qa_center/workers/runner_supervisor.py`**（258 行）— 子进程编排：_RUNNERS 全局表、execute_ui_case 流程、abort 机制、watchdog + stderr drain
5. **`backend/qa_center/locust_runner.py`**（414 行）— 性能测试：动态生成 locustfile、文件 IPC、percentile 计算、monitor 线程
6. **`backend/qa_center/views_devops.py`**（908 行）— DevOps 平台四块：Dashboard 聚合、CI/CD 配置、Pipeline 触发/Webhook、TestTask 编排

附加（如果时间够）：
7. `backend/qa_center/unified_assertions.py`（715 行）— 断言引擎，_smart_eq 容错
8. `backend/qa_center/template_engine.py`（151 行）— 变量池 + `{{var}}` 渲染
9. `backend/room/consumers.py`（133 行）— BoardConsumer 鉴权 + 广播范式
10. `frontend/src/stores/composables/useWebSocket.ts`（139 行）— 前端 WS 通用封装：心跳 + 重连 + 观察者

---

## 结语

这份文档覆盖了 SyncBoard 六个最有技术含量的模块，每章自带数据流图 + 代码引用 + 设计权衡 + 问答库。

**用法建议**：
- 第一遍：通读 0 / 1 / 7 三章（架构 → WS → 端到端），建立全局图景
- 第二遍：按模块挑选（如答辩前一晚重点看 3 / 4 / 5）
- 第三遍：对着问答库自测，能讲到行号级
- 真讲的时候：手边打开本文档 + 必读 6 文件，按章节顺讲

**如果有人问"项目里你最得意的设计是什么"**，可以从这几个里挑：
- WebSocket 只传通知不传数据（避免双写）
- AI 工具调用 3 轮循环 + 异常分级
- 新版 API 执行器的变量池三层优先级 + 模板引擎
- Playwright 子进程 + JSON Lines IPC + 全局 _RUNNERS 表
- Locust 动态生成 + 文件 IPC + 0.5s 监控线程
- 自动 Bug 创建的去重逻辑（按三元组）

**已知 TODO（答辩时要诚实）**：
- Pipeline 还是 mock 没接真 Jenkins
- TestTask 用 threading 不用 Celery（重启丢任务）
- 性能测试同时只能跑一个用例（固定文件名）
- Dashboard 大查询没缓存
- 跨 suite 变量传递没做

