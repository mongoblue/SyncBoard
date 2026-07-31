# SyncBoard (FlowSpace) 系统开发文档

> **面向学习者**：本文档从零开始，逐层深入讲解 SyncBoard 企业级项目协作平台的完整技术实现。适合具备 Python/Django 和 Vue 基础的开发者，作为深入学习和二次开发的参考手册。

---

## 目录

- [第一部分：系统概览](#第一部分系统概览)
- [第二部分：后端架构详解](#第二部分后端架构详解)
- [第三部分：前端架构详解](#第三部分前端架构详解)
- [第四部分：核心业务流程走读](#第四部分核心业务流程走读)
- [第五部分：开发环境搭建](#第五部分开发环境搭建)
- [第六部分：测试体系](#第六部分测试体系)
- [第七部分：部署与运维](#第七部分部署与运维)
- [第八部分：扩展指南](#第八部分扩展指南)

---

# 第一部分：系统概览

## 1.1 项目定位

**SyncBoard**（品牌名 **FlowSpace**）是一个企业级全栈项目协作看板系统。它不仅仅是一个任务管理工具，更是一个整合了 **看板协作 + AI 助手 + QA 质量中心 + DevOps 平台 + Bug 追踪 + RBAC 权限** 的综合平台。

### 核心设计理念

1. **实时性优先**：所有协作操作（任务移动、评论、分配）通过 WebSocket 实时广播，而非轮询
2. **模块正交**：四个 Django App 职责清晰，互不侵入（room / qa_center / bug_tracker / system）
3. **安全纵深防御**：从 DRF 全局限流 → 视图级鉴权 → WebSocket 项目鉴权 → 文件上传安全，层层设防
4. **前后端分离但紧密协作**：REST API 负责数据读写，WebSocket 负责实时通知，各司其职

## 1.2 技术选型

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **后端框架** | Django 6 + DRF | 成熟生态、ORM 强大、自带 Admin、Channels 支持好 |
| **实时通信** | Django Channels + Redis Channel Layer | 原生集成、消费模式清晰、无需引入额外服务 |
| **任务队列** | Celery + Redis | 异步执行测试/搜索索引更新、Beat 支持定时任务 |
| **数据库** | MySQL 8.0 | 成熟稳定、UUID 支持好、事务完整 |
| **搜索引擎** | Elasticsearch 7 + Haystack + jieba | 中文全文搜索、DSL 查询灵活 |
| **前端框架** | Vue 3 (Composition API) + TypeScript | 类型安全、`<script setup>` 简洁、生态丰富 |
| **UI 组件** | Element Plus 2 | 成熟的企业级组件库、暗色模式支持 |
| **状态管理** | Pinia 3 | Vue 3 官方推荐、组合式 API 风格、模块化拆分 |
| **构建工具** | Vite 7 | 极速冷启动、HMR 快、原生 ESM |
| **容器化** | Docker Compose | 一键启动 6 个服务、开发环境一致 |
| **图表** | ECharts 6 | 雷达图、燃尽图、趋势图一站式 |

## 1.3 系统全景架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Nginx (Production)                            │
│                    / → Vue SPA   /api → Backend   /ws → Backend         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │   Vue 3 SPA     │    │  Django ASGI    │    │  Celery Worker  │
   │   (Vite)        │    │  (Uvicorn)      │    │  (Redis Queue)  │
   │                  │    │                  │    │                  │
   │ ┌─────────────┐ │    │ ┌──────────────┐ │    │ ┌──────────────┐ │
   │ │  Pinia      │ │    │ │  4 Apps      │ │    │ │ 测试执行     │ │
   │ │  Router     │ │    │ │  - room      │ │    │ │ 搜索索引     │ │
   │ │  Element+   │ │◄───►│ │  - qa_center │ │◄───►│ │ 定时任务     │ │
   │ │  ECharts    │ │REST │ │  - bug_track │ │    │ │              │ │
   │ │  Axios      │ │+ WS │ │  - system    │ │    │ └──────────────┘ │
   │ └─────────────┘ │    │ └──────────────┘ │    └─────────────────┘
   └─────────────────┘    └────────┬─────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   ┌───────────┐           ┌───────────┐           ┌───────────────┐
   │  MySQL 8  │           │  Redis 7  │           │ Elasticsearch │
   │  (主存储)  │           │ (Cache/WS │           │    7.17       │
   │           │           │  /Celery)  │           │  (全文搜索)   │
   └───────────┘           └───────────┘           └───────────────┘
```

### 通信模式

```
┌──────────┐   REST (读写)    ┌──────────┐   WS (通知)    ┌──────────┐
│ Client A │ ──────────────► │  Django  │ ─────────────► │ Client B │
│          │ ◄────────────── │  Backend │ ◄───────────── │          │
└──────────┘   JSON 响应     └──────────┘   "refresh"    └──────────┘
                                 │
                                 ▼
                           ┌──────────┐
                           │  MySQL   │  ← 数据持久化
                           └──────────┘
```

> **关键设计原则**：WebSocket 只传输**通知信号**（如 "任务 X 已更新"），不传输完整数据。客户端收到通知后通过 REST API 重新拉取最新数据。这保证了数据一致性和前端状态可靠性。

## 1.4 功能模块全景

| 模块 | Django App | 前端路由前缀 | 关键能力 |
|------|-----------|-------------|----------|
| **看板协作** | `room` | `/projects/:id/board` | 拖拽排序、任务详情、标签、筛选搜索 |
| **实时同步** | `room` (WS) | 全局 | WebSocket 广播、心跳重连、观察者模式 |
| **团队协作** | `room` | `/projects/:id/members` | 评论嵌套、活动日志、文件附件、四级角色 |
| **AI 助手** | `room` | `/projects/:id/ai-chat` | RAG 检索、流式 SSE、Tool Calling、项目分析 |
| **迭代管理** | `room` | `/projects/:id/sprints` | Sprint CRUD、燃尽图、任务分配 |
| **QA 测试** | `qa_center` | `/projects/:id/qa/*` | API/UI/性能测试、录制器、批量执行 |
| **DevOps** | `qa_center` | `/projects/:id/qa/devops` | CI/CD 配置、Pipeline、定时任务、质量报告 |
| **Bug 追踪** | `bug_tracker` | `/projects/:id/bugs/*` | 9 状态状态机、自动建 Bug、工作台 |
| **RBAC 权限** | `system` | `/projects/:id/system/*` | 菜单/角色/用户、方法级鉴权 |
| **通知系统** | `room` (WS) | `/projects/:id/notifications` | 8 种通知类型、已读/未读、全局广播 |

---

# 第二部分：后端架构详解

## 2.1 Django 项目配置 (`backend/backend/settings.py`)

### 2.1.1 中间件栈

```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # ① CORS — 最先处理
    'django.middleware.security.SecurityMiddleware',  # ② 安全头
    'whitenoise.middleware.WhiteNoiseMiddleware',     # ③ 静态文件
    'django.contrib.sessions.middleware.SessionMiddleware',  # ④ Session
    'django.middleware.common.CommonMiddleware',      # ⑤ URL 规范化
    'django.middleware.csrf.CsrfViewMiddleware',      # ⑥ CSRF 保护
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # ⑦ 用户认证
    'django.contrib.messages.middleware.MessageMiddleware',  # ⑧ 消息
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # ⑨ 防点击劫持
]
```

> **为什么 CorsMiddleware 在最前面？**  Django 中间件按顺序执行（请求从上到下，响应从下到上）。CORS 需要在最外层捕获 OPTIONS 预检请求，避免后续中间件（如 CSRF）拒绝它们。

### 2.1.2 DRF 配置

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'backend.authentication.CsrfExemptSessionAuthentication',  # 自定义: 豁免 CSRF
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',  # 全局: 必须登录
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',   # 匿名: 100/min
        'rest_framework.throttling.UserRateThrottle',   # 认证: 1000/min
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
        'user': '1000/minute',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': 'backend.utils.custom_exception_handler',
}
```

**自定义 CSRF 豁免认证** (`backend/authentication.py`)：
```python
class CsrfExemptSessionAuthentication(SessionAuthentication):
    """继承 DRF SessionAuthentication，但不强制 CSRF 检查。
    因为前端通过 Axios 的 withCredentials + X-CSRFToken 头自行处理 CSRF。
    """
    def enforce_csrf(self, request):
        return  # 跳过 DRF 的 CSRF 强制检查，交给 Django CsrfViewMiddleware
```

### 2.1.3 Channels (WebSocket) 配置

```python
# ASGI 应用入口 — backend/asgi.py
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

application = ProtocolTypeRouter({
    "http": django_asgi_app,     # HTTP 请求 → Django 视图
    "websocket": AllowedHostsOriginValidator(  # WebSocket → Channels
        AuthMiddlewareStack(     # 注入 request.user
            URLRouter(
                room.routing.websocket_urlpatterns +
                qa_center.routing.websocket_urlpatterns
            )
        )
    ),
})
```

```python
# Channel Layer 配置 — 使用 Redis 作为后端
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, 6379)],
        },
    },
}
```

### 2.1.4 Celery 配置

```python
# backend/celery.py
CELERY_BROKER_URL = f'redis://{REDIS_HOST}:6379/0'
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Shanghai'
```

## 2.2 四应用的职责划分

```
backend/
├── room/          # 核心业务 — 看板、项目、任务、评论、AI、Sprint、通知
├── qa_center/     # 质量中心 — API/UI/性能测试、DevOps、CI/CD、质量报告
├── bug_tracker/   # 缺陷追踪 — Bug CRUD、状态机、关联测试
├── system/        # 系统管理 — RBAC 菜单/角色/用户
└── tests/         # 跨应用集成测试
```

### 应用间交互约定

```
room ←── qa_center (测试结果关联任务)
room ←── bug_tracker (Bug 关联任务)
system ──→ 所有应用 (权限检查)
```

> **设计原则**：应用间通过 REST API 或模型外键进行松耦合交互，避免循环导入。`system` 应用只被其他应用引用权限码，不反向依赖。

## 2.3 数据模型设计

### 2.3.1 UUID 主键 vs 自增主键

SyncBoard 混合使用两种主键策略：

| 实体 | 主键类型 | 原因 |
|------|---------|------|
| Project, Column, Task | **UUID** | 需要在前后端之间安全暴露 ID，防止枚举攻击 |
| Tag, Comment, Sprint | **自增 Integer** | 项目内实体，ID 不暴露在公开 URL |
| QA 模型 | **自增 Integer** | 大量数据，索引效率优先 |

```python
# UUID 主键 — room/models.py
import uuid

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

class Column(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

### 2.3.2 核心 ER 关系

```
Project (1) ──────< Column (N) ──────< Task (N) >────── TaskComment (N)
    │                                     │
    │                                     ├────── TaskAttachment (N)
    │                                     ├────── TaskActivityLog (N)
    │                                     └────── Tag (N:M)
    │
    ├────── ProjectRole (N) ──────< ProjectMember (N) >── User
    ├────── Sprint (N) ──────< SprintTask (N:M)
    ├────── AIConversation (N)
    ├────── Notification (N)
    └────── ProjectApiDoc (N)
```

### 2.3.3 Float Position 排序算法

看板任务排序使用**分数位置算法**，支持在任意两个任务之间插入：

```python
# 初始位置间隔
POSITION_GAP = 65536  # 2^16

def calculate_position(prev_task, next_task):
    """计算新任务的位置分数"""
    if not prev_task and not next_task:
        return POSITION_GAP  # 第一个任务
    if not prev_task:
        return next_task.position / 2  # 插入到最前面
    if not next_task:
        return prev_task.position + POSITION_GAP  # 追加到最后面
    return (prev_task.position + next_task.position) / 2  # 插入到中间
```

> **为什么不用整数序号？** 如果使用 1, 2, 3... 排序，在 1 和 2 之间插入需要重排所有后续任务。Float 方案只需计算平均值，O(1) 即可插入。

## 2.4 DRF 视图层设计模式

### 2.4.1 三种视图模式的选择

| 模式 | 示例 | 适用场景 |
|------|------|----------|
| **函数视图 + 装饰器** | `room/views/auth.py` | 简单端点（登录/登出） |
| **APIView 类** | `room/views/board.py` | 需要 `get/post/patch/delete` 混合逻辑 |
| **ViewSet + Router** | `bug_tracker/views.py` | 标准 CRUD（Bug, TestCase） |

**示例：函数视图**
```python
# room/views/auth.py
@api_view(['POST'])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    """登录接口 — 使用自定义限流"""
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(request, username=username, password=password)
    if user:
        login(request, user)
        return Response({'user': UserSerializer(user).data})
    raise AuthenticationFailed('用户名或密码错误')
```

**示例：ViewSet**
```python
# bug_tracker/views.py
class BugViewSet(viewsets.ModelViewSet):
    """Bug CRUD — 使用 DRF ViewSet 自动路由"""
    queryset = Bug.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return BugListSerializer      # 列表：精简字段
        elif self.action == 'create':
            return BugCreateSerializer     # 创建：仅必要字段
        elif self.action in ('update', 'partial_update'):
            return BugUpdateSerializer     # 更新：部分字段可写
        return BugDetailSerializer         # 详情：完整嵌套

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        """自定义动作: 状态流转"""
        bug = self.get_object()
        to_status = request.data.get('to_status')
        validate_transition(bug.status, to_status)
        bug.status = to_status
        bug.save()
        return Response(BugDetailSerializer(bug).data)
```

### 2.4.2 项目鉴权 Mixin

```python
# room/views/mixins.py
class ProjectAccessMixin:
    """所有需要项目上下文的视图都继承此 Mixin"""
    
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        project_id = self.kwargs.get('project_id') or request.query_params.get('project')
        if project_id:
            self.project = ensure_project_id_access(request.user, project_id)
```

## 2.5 自定义异常处理与错误码

```python
# backend/api_errors.py
class APIError(Exception):
    """统一 API 错误"""
    def __init__(self, message, code='ERROR', status=400, details=None):
        self.message = message
        self.code = code
        self.status = status
        self.details = details

def error_response(message, code='ERROR', status=400, details=None):
    return Response({
        'error': True,
        'code': code,
        'message': message,
        'details': details,
    }, status=status)

# 常用快捷函数
def not_found(msg='资源不存在'):
    return error_response(msg, code='NOT_FOUND', status=404)

def permission_denied(msg='权限不足'):
    return error_response(msg, code='PERMISSION_DENIED', status=403)

def bad_request(msg='请求参数错误'):
    return error_response(msg, code='BAD_REQUEST', status=400)
```

```python
# backend/utils.py — 全局异常处理
def custom_exception_handler(exc, context):
    """将所有 DRF 异常转换为统一 JSON 格式"""
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            'error': True,
            'code': 'VALIDATION_ERROR' if response.status_code == 400 else 'ERROR',
            'message': str(exc),
            'details': response.data,
        }
    return response
```

## 2.6 认证与权限体系

### 2.6.1 三层权限模型

```
┌─────────────────────────────────────────────┐
│              ① 系统级 RBAC                    │
│  Menu → Role → User                          │
│  权限码: sys:menu:list, sys:user:edit...      │
│  控制: /api/system/* 的管理操作               │
├─────────────────────────────────────────────┤
│              ② 项目级 RBAC                    │
│  ProjectRole (Owner/Admin/Editor/Viewer)     │
│  ProjectMember (user + role)                 │
│  控制: /api/projects/:id/* 的操作            │
├─────────────────────────────────────────────┤
│              ③ WebSocket 鉴权                │
│  connect 时检查用户是否为项目成员              │
│  非成员 → close(code=4003)                   │
└─────────────────────────────────────────────┘
```

### 2.6.2 系统级 RBAC 实现

```python
# system/permissions.py
class HasSystemPermission(BasePermission):
    """检查用户是否拥有特定系统权限码"""
    
    def __init__(self, permission_code):
        self.permission_code = permission_code
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        profile = SystemUserProfile.objects.filter(user=request.user).first()
        if not profile:
            return False
        return profile.has_permission(self.permission_code)

# 使用方式 (system/views.py)
class MenuView(APIView):
    permission_classes = [HasSystemPermission('sys:menu:list')]
```

### 2.6.3 项目级 RBAC 实现

```python
# room/project_access.py
def ensure_project_id_access(user, project_id):
    """验证用户是项目成员，否则抛异常"""
    project = get_object_or_404(Project, id=project_id)
    if project.owner == user:
        return project
    if ProjectMember.objects.filter(project=project, user=user).exists():
        return project
    raise PermissionDenied('您不是该项目的成员')

def project_access_q(project_param, user):
    """构建 Django Q 对象，限制查询范围为用户可见项目"""
    return Q(owner=user) | Q(projectmember__user=user)
```

## 2.7 限流体系

```python
# backend/throttles.py

class LoginRateThrottle(AnonRateThrottle):
    """登录限流 — 5次/分钟（CI 环境放开到 10000）"""
    rate = '5/minute' if not os.getenv('CI') else '10000/minute'

class AIRateThrottle(UserRateThrottle):
    """AI 限流 — 20次/分钟（保护 API 费用）"""
    rate = '20/minute'

class WebSocketConnectThrottle(SimpleRateThrottle):
    """WebSocket 连接限流 — 30次/分钟"""
    rate = '30/minute'
    scope = 'ws_connect'
    
    def get_cache_key(self, scope, consumer):
        return f'ws_{scope["user"].id}'
```

## 2.8 WebSocket 层设计

### 2.8.1 Consumer 实现模式

```python
# room/consumers.py — 看板消费者
class BoardConsumer(AsyncWebsocketConsumer):
    """看板房间 WebSocket 消费者
    
    路由: /ws/board/<project_id>/
    组名: board_<project_id>
    """
    
    async def connect(self):
        """连接时鉴权 + 加入房间组"""
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.room_group_name = f'board_{self.project_id}'
        
        # 鉴权：检查用户是否为项目成员
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close(code=4001)
            return
        
        try:
            ensure_project_id_access(user, self.project_id)
        except PermissionDenied:
            await self.close(code=4003)  # 非项目成员
            return
        
        # 加入 Channel Layer 组
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
    
    async def receive(self, text_data):
        """接收客户端消息（如心跳）"""
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))
    
    async def broadcast_refresh(self, event):
        """向组内所有客户端广播刷新信号"""
        await self.send(text_data=json.dumps({
            'type': 'refresh',
            'task_id': event.get('task_id'),
            'action': event.get('action'),
        }))
```

### 2.8.2 触发 WebSocket 广播

```python
# room/views/comment.py — 创建评论后广播
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

@api_view(['POST'])
def create_comment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    serializer = TaskCommentSerializer(data=request.data)
    serializer.save(task=task, author=request.user)
    
    # 通过 Channel Layer 向看板组广播
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'board_{task.column.project.id}',
        {
            'type': 'broadcast_refresh',
            'task_id': str(task_id),
            'action': 'comment_added',
        }
    )
    return Response(serializer.data)
```

## 2.9 Celery 异步任务

```python
# backend/tasks.py — 搜索索引异步更新
from celery import shared_task

@shared_task
def update_search_index(model_name, instance_id):
    """异步更新 Elasticsearch 索引"""
    from haystack import connections
    index = connections['default'].get_unified_index().get_index(
        apps.get_model(*model_name.split('.'))
    )
    instance = index.get_model().objects.get(id=instance_id)
    index.update_object(instance)

@shared_task
def remove_from_search_index(model_name, instance_id):
    """异步从索引中删除"""
    ...
```

```python
# qa_center/tasks.py — 测试执行任务
@shared_task(bind=True, max_retries=3)
def execute_test_suite(self, suite_id, environment_id=None):
    """异步执行 API 测试套件"""
    suite = ApiAutoTestSuite.objects.get(id=suite_id)
    runner = ApiTestRunner(suite, environment_id)
    result = runner.execute()
    return result.id
```

## 2.10 文件上传安全

```python
# room/views/attachment.py
import imghdr
from PIL import Image
import io

ALLOWED_CONTENT_TYPES = {
    'image/jpeg', 'image/png', 'image/gif',
    'application/pdf', 'text/plain',
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_uploaded_file(file):
    """文件安全校验三部曲"""
    
    # ① 大小检查
    if file.size > MAX_FILE_SIZE:
        raise ValidationError('文件大小超过 10MB 限制')
    
    # ② MIME 类型白名单
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(f'不支持的文件类型: {file.content_type}')
    
    # ③ 图片文件: 重编码验证（防止图片马）
    if file.content_type.startswith('image/'):
        try:
            img = Image.open(file)
            img.verify()  # 验证图片完整性
            file.seek(0)
            # 可选: 重编码为 PNG 去除恶意数据
            output = io.BytesIO()
            img = Image.open(file)
            img.save(output, format='PNG')
            file.file = output
        except Exception:
            raise ValidationError('文件损坏或不是有效的图片')
```

---

# 第三部分：前端架构详解

## 3.1 Vue 3 项目初始化

```typescript
// frontend/src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { setupDirectives } from './directives'
import App from './App.vue'
import 'element-plus/dist/index.css'
import './styles/global.css'

const app = createApp(App)

// 安装顺序: Pinia → Router → Element Plus → 自定义指令
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
}

setupDirectives(app)
app.mount('#app')
```

## 3.2 路由设计

```typescript
// frontend/src/router/index.ts
const routes = [
    { path: '/login', component: () => import('@/views/Login.vue') },
    { path: '/projects', component: () => import('@/views/Projects.vue'), meta: { requiresAuth: true } },
    {
        path: '/projects/:projectId',
        component: () => import('@/views/ProjectLayout.vue'),
        meta: { requiresAuth: true },
        children: [
            { path: '', redirect: 'board' },
            { path: 'board', component: () => import('@/views/Board.vue') },
            { path: 'members', component: () => import('@/views/Members.vue') },
            { path: 'qa', component: () => import('@/views/qa/QA.vue') },
            { path: 'bugs', component: () => import('@/views/bug/BugWorkbench.vue') },
            { path: 'bugs/:id', component: () => import('@/views/bug/BugDetail.vue') },
            {
                path: 'system/menu',
                component: () => import('@/views/system/MenuManagement.vue'),
                meta: { permission: 'sys:menu:list' }  // 权限守卫
            },
            // ... 40+ 路由
        ]
    },
]

// 全局导航守卫
router.beforeEach(async (to, from, next) => {
    const authStore = useAuthStore()
    
    if (!authStore.user && to.path !== '/login') {
        await authStore.checkAuth()  // 从 Cookie 恢复登录态
    }
    
    if (to.meta.requiresAuth && !authStore.user) {
        return next('/login')  // 未登录 → 登录页
    }
    
    if (authStore.user && to.path === '/login') {
        return next('/projects')  // 已登录 → 项目列表
    }
    
    if (to.meta.permission && !authStore.checkPermission(to.meta.permission as string)) {
        console.warn(`缺少权限: ${to.meta.permission}`)
        return next(from.path)  // 权限不足 → 停留在当前页
    }
    
    next()
})
```

## 3.3 Pinia 状态管理

### 3.3.1 模块化 Store 设计

```
stores/
├── Auth.ts          # 认证 + 系统权限
├── notification.ts  # 全局通知 WebSocket
└── board/
    ├── index.ts     # 聚合 Store — 组合子 Store + WS 连接
    ├── column.ts    # 看板列 CRUD
    ├── task.ts      # 任务 CRUD
    ├── tag.ts       # 标签 CRUD
    ├── user.ts      # 用户列表
    └── types.ts     # 类型定义
```

### 3.3.2 聚合 Store 模式

```typescript
// stores/board/index.ts
export const useBoardStore = defineStore('board', () => {
    const columnStore = useBoardColumnStore()
    const taskStore = useBoardTaskStore()
    const tagStore = useBoardTagStore()
    const userStore = useBoardUserStore()
    
    const projectId = ref<string>('')
    const { isConnected, connect, disconnect } = useWebSocket()
    
    // 初始化: 项目切换时重新加载所有数据 + 建立 WS 连接
    async function init(pid: string) {
        projectId.value = pid
        await Promise.all([
            columnStore.fetchColumns(pid),
            tagStore.fetchTags(pid),
            userStore.fetchUsers(pid),
        ])
        await taskStore.fetchTasks(pid)
        connect(pid)  // 建立 WebSocket 连接
    }
    
    // WS 监听器: 收到 refresh 信号则重新拉取任务
    function setupWSListeners() {
        addMessageListener((msg) => {
            if (msg.type === 'refresh') {
                taskStore.fetchTasks(projectId.value)
            }
        })
    }
    
    return {
        projectId, isConnected,
        // 暴露子 Store
        columns: columnStore.columns,
        tasks: taskStore.tasks,
        tags: tagStore.tags,
        // 方法
        init, connect, disconnect,
    }
})
```

## 3.4 API 通信层

```typescript
// utils/request.ts
import axios from 'axios'

const request = axios.create({
    baseURL: '/api',            // Vite 代理到 localhost:8000
    timeout: 60000,
    withCredentials: true,      // 携带 Cookie (Session)
    xsrfCookieName: 'csrftoken',
    xsrfHeaderName: 'X-CSRFToken',
})

// 响应拦截器 — 自动解包 data
request.interceptors.response.use(
    (response) => {
        return response.data  // 组件直接拿到业务数据
    },
    (error) => {
        if (error.response?.status === 401) {
            // Token 过期 → 跳登录
            window.location.href = '/login'
        }
        return Promise.reject(error)
    }
)

export default request
```

## 3.5 WebSocket 客户端

```typescript
// stores/composables/useWebSocket.ts
export function useWebSocket() {
    const isConnected = ref(false)
    const listeners = new Set<(msg: any) => void>()
    let ws: WebSocket | null = null
    let heartbeatTimer: number | null = null
    let reconnectTimer: number | null = null
    
    function connect(projectId: string) {
        const url = wsHost(`/ws/board/${projectId}/`)
        ws = new WebSocket(url)
        
        ws.onopen = () => {
            isConnected.value = true
            startHeartbeat()
        }
        
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data)
            if (msg.type === 'pong') return  // 忽略心跳响应
            listeners.forEach(fn => fn(msg))  // 通知所有观察者
        }
        
        ws.onclose = () => {
            isConnected.value = false
            stopHeartbeat()
            scheduleReconnect(projectId)
        }
    }
    
    // 心跳: 每 30 秒发送 ping
    function startHeartbeat() {
        heartbeatTimer = setInterval(() => {
            ws?.send(JSON.stringify({ type: 'ping' }))
        }, 30000)
    }
    
    // 重连: 3 秒后自动重连
    function scheduleReconnect(projectId: string) {
        reconnectTimer = setTimeout(() => connect(projectId), 3000)
    }
    
    // 观察者模式: 注册/注销消息监听器
    function addMessageListener(fn: (msg: any) => void) {
        listeners.add(fn)
    }
    function removeMessageListener(fn: (msg: any) => void) {
        listeners.delete(fn)
    }
    
    function disconnect() {
        clearInterval(heartbeatTimer!)
        clearTimeout(reconnectTimer!)
        ws?.close()
    }
    
    return { isConnected, connect, disconnect, addMessageListener, removeMessageListener }
}
```

## 3.6 自定义指令

```typescript
// directives/permission.ts
import type { Directive, DirectiveBinding } from 'vue'

const hasPermission = (perm: string): boolean => {
    const authStore = useAuthStore()
    return authStore.permissions.includes(perm)
}

// v-permission: 单一权限检查
const vPermission: Directive = {
    mounted(el: HTMLElement, binding: DirectiveBinding) {
        if (!hasPermission(binding.value)) {
            el.parentNode?.removeChild(el)  // 无权限则移除 DOM
        }
    }
}

// v-permission-all: 需要全部权限
const vPermissionAll: Directive = {
    mounted(el: HTMLElement, binding: DirectiveBinding) {
        const perms: string[] = binding.value
        if (!perms.every(hasPermission)) {
            el.parentNode?.removeChild(el)
        }
    }
}

// v-permission-any: 需要任一权限
const vPermissionAny: Directive = {
    mounted(el: HTMLElement, binding: DirectiveBinding) {
        const perms: string[] = binding.value
        if (!perms.some(hasPermission)) {
            el.parentNode?.removeChild(el)
        }
    }
}

// 注册
export function setupDirectives(app: App) {
    app.directive('permission', vPermission)
    app.directive('permission-all', vPermissionAll)
    app.directive('permission-any', vPermissionAny)
}
```

使用示例：
```html
<el-button v-permission="'sys:user:add'">新增用户</el-button>
<el-button v-permission-all="['sys:role:list', 'sys:role:edit']">编辑角色</el-button>
```

## 3.7 样式体系

### 3.7.1 CSS 变量暗色模式

```css
/* styles/variables.css */
:root {
    --color-primary: #0F766E;       /* 主题色 — 深青 */
    --color-bg: #F8FAFC;
    --color-surface: #FFFFFF;
    --color-text: #1E293B;
    --color-text-secondary: #64748B;
    --color-border: #E2E8F0;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
}

[data-theme="dark"] {
    --color-bg: #0F172A;
    --color-surface: #1E293B;
    --color-text: #E2E8F0;
    --color-text-secondary: #94A3B8;
    --color-border: #334155;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.2);
}
```

### 3.7.2 Element Plus 全局覆写

```css
/* styles/element-overrides.css */
/* 统一按钮圆角 */
.el-button { border-radius: 8px; }
/* 输入框聚焦色 */
.el-input__wrapper.is-focus { box-shadow: 0 0 0 1px var(--color-primary) inset; }
/* 表格行悬停 */
.el-table__body tr:hover > td { background-color: rgba(15, 119, 110, 0.04); }
```

## 3.8 ECharts 集成

```vue
<!-- views/ProjectQualityReport.vue -->
<template>
  <div ref="radarChart" style="width:100%;height:400px"></div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, ref, watch } from 'vue'

const radarChart = ref<HTMLElement>()
let chart: echarts.ECharts

function renderRadar(data: any) {
    chart = echarts.init(radarChart.value!)
    chart.setOption({
        radar: {
            indicator: [
                { name: '测试覆盖', max: 100 },
                { name: '通过率', max: 100 },
                { name: '性能', max: 100 },
                { name: 'Bug密度', max: 100 },
                { name: '部署成功率', max: 100 },
            ]
        },
        series: [{
            type: 'radar',
            data: [{ value: data.scores, name: '当前项目' }],
            areaStyle: { color: 'rgba(15, 119, 110, 0.2)' },
            itemStyle: { color: '#0F766E' },
        }]
    })
}

onMounted(() => renderRadar(props.data))
watch(() => props.data, (newData) => renderRadar(newData))
</script>
```

---

# 第四部分：核心业务流程走读

## 4.1 看板拖拽排序

```
┌──────────────┐   dragend    ┌──────────────┐   PATCH /api/tasks/:id/   ┌──────────────┐
│  Vue 组件     │ ──────────► │  Board Store  │ ────────────────────────► │  Django View │
│  vuedraggable │              │  (optimistic  │                           │  board.py    │
│               │              │   UI update)  │                           │              │
└──────────────┘              └──────────────┘                           └──────┬───────┘
                                                                               │
                                         ┌─────────────────────────────────────┤
                                         ▼                                     ▼
                                  ┌──────────┐                          ┌──────────────┐
                                  │  MySQL   │                          │ Channel Layer│
                                  │ position │                          │ group_send() │
                                  │ 更新     │                          │ "refresh"    │
                                  └──────────┘                          └──────┬───────┘
                                                                               │
┌──────────────┐                                                      ┌──────────────┐
│  其他客户端   │ ◄──── refresh ──── fetchTasks() ──── 重新渲染 ────── │ BoardConsumer│
│  UI 更新     │                                                      │ 广播         │
└──────────────┘                                                      └──────────────┘
```

```typescript
// 前端 — Board.vue (vuedraggable)
async function onDragEnd(evt: any) {
    const task = evt.item.__draggable_context.element
    const newColumnId = evt.to.dataset.columnId
    const prevTask = evt.to.children[evt.newIndex - 1]?.__draggable_context?.element
    const nextTask = evt.to.children[evt.newIndex + 1]?.__draggable_context?.element
    
    // 计算新位置
    const newPosition = calculatePosition(prevTask?.position, nextTask?.position)
    
    // 乐观更新: 立即修改本地状态
    taskStore.moveTask(task.id, newColumnId, newPosition)
    
    // 发送 REST 请求
    await request.patch(`/tasks/${task.id}/`, {
        column_id: newColumnId,
        position: newPosition,
    })
    // WS 广播由后端负责，其他客户端自动收到 refresh
}
```

## 4.2 AI 对话流程

```
┌─────────┐   "有哪些高优任务?"  ┌──────────┐   search(question)  ┌───────────────┐
│  用户    │ ──────────────────► │  Django   │ ─────────────────► │ Elasticsearch │
│         │                     │  ai.py    │ ◄───────────────── │ (RAG 检索)    │
│         │                     │           │   top_k 相关文档    └───────────────┘
│         │                     │           │
│         │  SSE: 目前有▌       │  POST     │  system_prompt + context + question
│         │ ◄────────────────── │  DeepSeek │ ◄────────────────────────────────┐
│         │  SSE: 目前有3个▌    │  API      │                                  │
│         │ ◄────────────────── │  (stream) │  ┌───────────────────────────┐   │
│         │  SSE: 目前有3个...  │           │  │ Tool Calling              │   │
│         │ ◄────────────────── │           │  │ - create_task(title, ...) │   │
│         │                     │           │  │ - search_tasks(query)     │   │
└─────────┘                     └──────────┘  │ - trigger_pipeline(...)   │   │
                                              └───────────────────────────┘   │
                                                                              │
  流程:                                                                        │
  1. 用户提问 → 后端从 ES 检索 top_k 相关任务/文档                               │
  2. 拼接 system prompt + context + question → 请求 DeepSeek API (stream=True) │
  3. 逐 token 通过 SSE (Server-Sent Events) 流式返回前端                         │
  4. 若 AI 返回 tool_calls → execute_tool() 执行本地操作 → 结果再发送给 AI       │
```

## 4.3 API 测试执行流程

```
POST /api/qa/auto-execute/
{ suite_id: 1, environment_id: 2 }
         │
         ▼
┌─────────────────────┐
│ 1. 模板引擎渲染      │  替换 {{base_url}}, {{token}} 等变量
│    template_engine   │
├─────────────────────┤
│ 2. HTTP 请求执行     │  requests.get/post/put/delete
│    transports.py    │  支持 headers/cookies/query_params/timeout
├─────────────────────┤
│ 3. 断言判断          │  JSONPath 提取 → 与 expected_value 比较
│    assertion_core/  │  支持: equals/contains/regex/greater_than/...
├─────────────────────┤
│ 4. 变量提取          │  从响应中提取变量 → 存入变量池 → 后续用例使用
│    extractors       │  支持: jsonpath/header/cookie/regex/status_code
├─────────────────────┤
│ 5. 结果持久化        │  ApiAutoTestCaseResult (请求/响应快照 + curl)
│    models.py        │  ApiAutoTestResult (套件聚合结果)
├─────────────────────┤
│ 6. 失败自动建 Bug    │  如果 assertion 失败:
│    bug_utils.py     │  Bug.objects.create(
│                     │      source_test_type='api',
│                     │      source_case_id=case.id,
│                     │      source_result_id=result.id,
│                     │  )
└─────────────────────┘
```

## 4.4 Bug 状态流转

```
                          ┌──────────┐
                          │   open   │  ← 新建 Bug
                          └────┬─────┘
                               │ confirm
                               ▼
                          ┌──────────┐
               ┌─────────│confirmed │─────────┐
               │ reject  └────┬─────┘ reject  │
               ▼              │               ▼
          ┌──────────┐        │          ┌───────────┐
          │ rejected │   start│          │ duplicate │
          └──────────┘        ▼          └───────────┘
                        ┌──────────┐
                        │in_progress│
                        └────┬─────┘
                             │ fix
                             ▼
                        ┌──────────┐
                        │  fixed   │
                        └────┬─────┘
                             │ test
                             ▼
                        ┌──────────┐
                        │ testing  │
                        └────┬─────┘
                       ┌─────┴─────┐
                 reopen│           │ verify
                       ▼           ▼
                  ┌────────┐  ┌──────────┐
                  │  open  │  │ verified │
                  └────────┘  └────┬─────┘
                                   │ close
                                   ▼
                              ┌──────────┐
                              │  closed  │  ← 终态
                              └──────────┘
```

```python
# bug_tracker/state_machine.py
BUG_TRANSITIONS = {
    'open':        ['confirmed', 'rejected', 'duplicate'],
    'confirmed':   ['in_progress', 'rejected', 'duplicate'],
    'in_progress': ['fixed'],
    'fixed':       ['testing'],
    'testing':     ['verified', 'open'],     # 可打回
    'verified':    ['closed'],
    'closed':      [],                        # 终态
    'rejected':    [],                        # 终态
    'duplicate':   [],                        # 终态
}

def validate_transition(from_status, to_status):
    allowed = BUG_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        raise TransitionError(
            f'不允许从 {from_status} 转换到 {to_status}，'
            f'允许的目标状态: {allowed}'
        )
```

## 4.5 实时通知链路

```
Django Signal (post_save)
    │
    ▼
Notification.objects.create(user=target_user, type='task_assigned', ...)
    │
    ▼
async_to_sync(channel_layer.group_send)(
    f'notifications_{target_user.id}',
    {'type': 'send_notification', 'notification': serialized_data}
)
    │
    ▼
GlobalConsumer.send_notification(event)
    │
    ▼ (WebSocket)
前端 notification.ts Store
    │
    ▼
ElNotification({ title: '任务分配', message: '...' })  ← 浏览器弹窗
```

---

# 第五部分：开发环境搭建

## 5.1 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 20.19+ | 前端构建/开发 |
| MySQL | 8.0 | 主数据库 |
| Redis | 7.0+ | 缓存 / Channels / Celery |
| Elasticsearch | 7.17 (可选) | 全文搜索 |
| Git | 2.x | 版本管理 |

## 5.2 Docker 启动基础设施

```bash
# 克隆项目
git clone <repo-url> SyncBoard
cd SyncBoard

# 启动所有基础设施
docker-compose up -d db redis elasticsearch

# 验证服务
docker-compose ps
# NAME                STATE     PORTS
# syncboard-db-1      running   0.0.0.0:3306->3306/tcp
# syncboard-redis-1   running   0.0.0.0:6379->6379/tcp
# syncboard-es-1      running   0.0.0.0:9200->9200/tcp
```

## 5.3 后端初始化

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate      # Linux/macOS
# .\venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env — 填入你的 DB_PASSWORD、REDIS_HOST 等

# 数据库迁移
python manage.py migrate

# 创建管理员
python manage.py createsuperuser

# 可选: 初始化数据
python manage.py seed_ci_data          # 示例项目 + 任务 + 测试用例
python manage.py seed_bugs_demo        # 示例 Bug 数据
python manage.py init_rbac_data        # RBAC 菜单/角色/权限

# 启动开发服务器
uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload
```

## 5.4 前端初始化

```bash
cd frontend
npm install
npm run dev
# 浏览器访问: http://localhost:5173
```

> Vite 已配置代理：`/api` → `localhost:8000`，`/ws` → `localhost:8000`（含 WebSocket 升级），`/media` → `localhost:8000`

## 5.5 启动 Celery Worker

```bash
# 新终端
cd backend
source venv/bin/activate
celery -A backend worker -l info -P solo   # Windows 使用 solo pool
# Linux/macOS: celery -A backend worker -l info
```

## 5.6 Docker Compose 全栈模式

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 这将启动:
# - MySQL 8.0 (端口 3306)
# - Redis 7 (端口 6379)
# - Elasticsearch 7.17 (端口 9200)
# - Celery Worker
# - Django Backend (uvicorn, 端口 8000)
# - Vue Frontend (nginx, 端口 80)

# 访问 http://localhost
```

## 5.7 常见问题

| 问题 | 解决方案 |
|------|----------|
| `mysqlclient` 安装失败 | Ubuntu: `apt install libmysqlclient-dev` / Mac: `brew install mysql-client` |
| WebSocket 连接失败 | 确认 Redis 已启动: `redis-cli ping` |
| 搜索功能不工作 | ES 可选，需手动启动 `docker-compose up -d elasticsearch` |
| Celery 任务不执行 | 确认已启动 Celery Worker + Redis |
| Windows Celery `-P solo` | Windows 不支持 fork，必须使用 solo/threads pool |
| 前端代理 502 | 确认后端 `uvicorn` 已启动在 8000 端口 |

---

# 第六部分：测试体系

## 6.1 测试分层概览

```
┌─────────────────────────────────────────┐
│               E2E 测试                    │
│         Playwright (10 个文件)            │
│    浏览器自动化: 登录 → 拖拽 → QA 流程     │
├─────────────────────────────────────────┤
│             前端单元测试                   │
│         Vitest (11 个文件)                │
│   组件渲染: BugDetail, DevOpsPlatform...  │
├─────────────────────────────────────────┤
│            后端集成/API 测试               │
│         pytest (37+ 个文件)               │
│    API 端点: auth, board, QA, DevOps...  │
├─────────────────────────────────────────┤
│              性能测试                     │
│            Locust                        │
│    压力测试: 并发用户、RPS、延迟分布       │
└─────────────────────────────────────────┘
```

## 6.2 后端测试 (pytest)

```bash
# 运行所有后端测试
cd backend
pytest tests/ -v

# 运行特定模块
pytest tests/test_auth.py -v
pytest tests/test_qa_auto.py -v

# 带覆盖率
pytest tests/ --cov=. --cov-report=html
```

**测试配置** (`backend/pytest.ini`):
```ini
[pytest]
DJANGO_SETTINGS_MODULE = backend.settings
addopts = --reuse-db --nomigrations
```

**API 测试示例**:
```python
# backend/tests/test_auth.py
import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_login_success(client, django_user_model):
    user = django_user_model.objects.create_user(username='test', password='test123')
    url = reverse('login')
    response = client.post(url, {'username': 'test', 'password': 'test123'})
    assert response.status_code == 200
    assert 'user' in response.data
```

## 6.3 前端测试 (Vitest)

```bash
cd frontend

# 运行所有测试
npm run test:run

# 开发模式 (热更新)
npm run test
```

**组件测试示例** (`frontend/src/__tests__/BugDetail.test.ts`):
```typescript
import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import BugDetail from '@/views/bug/BugDetail.vue'

describe('BugDetail', () => {
    it('renders bug title', async () => {
        vi.mock('@/api/bug', () => ({
            getBug: vi.fn().mockResolvedValue({
                id: 1, title: '登录页面崩溃', status: 'open', severity: 'critical'
            })
        }))
        
        const wrapper = mount(BugDetail, {
            props: { id: 1 }
        })
        await wrapper.vm.$nextTick()
        expect(wrapper.text()).toContain('登录页面崩溃')
    })
})
```

## 6.4 E2E 测试 (Playwright)

```bash
# 运行 E2E 测试
E2E_BASE_URL=http://localhost:5173 pytest e2e/ -v

# 运行特定流程
E2E_BASE_URL=http://localhost:5173 pytest e2e/test_task_crud.py -v
E2E_BASE_URL=http://localhost:5173 pytest e2e/test_bug_flow.py -v
```

## 6.5 性能测试 (Locust)

```bash
# 启动 Locust Web UI
cd backend/performance
locust -f locustfile.py

# 无界面模式
locust -f locustfile.py --headless -u 10 -r 2 --run-time 60s --host=http://localhost:8000

# 或在项目中通过 QA 中心 Web 界面配置和启动
```

---

# 第七部分：部署与运维

## 7.1 Docker 多阶段构建

### 前端 Dockerfile

```dockerfile
# frontend/Dockerfile
# === 阶段 1: 构建 ===
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build             # Vite 构建 → /app/dist

# === 阶段 2: 生产 ===
FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
```

### 后端 Dockerfile

```dockerfile
# backend/Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
# ↑ 包含 Playwright 浏览器，支持 UI 测试

RUN apt-get update && apt-get install -y \
    libmysqlclient-dev gcc
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
```

## 7.2 Docker Compose 服务编排

```yaml
# docker-compose.yml (核心结构)
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: syncboard
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    
  elasticsearch:
    image: elasticsearch:7.17.18
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      
  celery_worker:
    build: ./backend
    command: celery -A backend worker -l info
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_started }
      
  backend:
    build: ./backend
    command: uvicorn backend.asgi:application --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    depends_on:
      db: { condition: service_healthy }
      
  frontend:
    build: ./frontend
    ports: ["80:80"]
    depends_on: [backend]
```

## 7.3 Nginx 反向代理配置

```nginx
# frontend/nginx.conf
server {
    listen 80;
    server_name localhost;

    # Vue SPA 静态文件
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;  # SPA fallback
    }

    # API 代理到 Django
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 代理
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }

    # 媒体文件
    location /media/ {
        proxy_pass http://backend:8000;
    }
}
```

## 7.4 环境变量管理

```bash
# backend/.env.example
DEBUG=True
DJANGO_SECRET_KEY=change-this-in-production

DB_NAME=syncboard
DB_USER=root
DB_PASSWORD=changeme
DB_HOST=127.0.0.1   # Docker 中用 db

REDIS_HOST=127.0.0.1  # Docker 中用 redis

HAYSTACK_URL=http://127.0.0.1:9200/  # Docker 中用 elasticsearch

OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

## 7.5 CI/CD 流水线 (GitHub Actions — 已配置，暂禁用)

```yaml
# .github/workflows/ci.yml.disabled
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install flake8 && flake8 backend/
      
  backend-tests:
    runs-on: ubuntu-latest
    services:
      mysql: { image: mysql:8.0, env: { MYSQL_ROOT_PASSWORD: test, MYSQL_DATABASE: syncboard } }
      redis: { image: redis:7-alpine }
    steps:
      - run: cd backend && pytest tests/ -v
      
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - run: docker-compose up -d
      - run: E2E_BASE_URL=http://localhost:5173 pytest e2e/ -v
```

---

# 第八部分：扩展指南

## 8.1 如何新增一个 Django App

```bash
cd backend
python manage.py startapp my_module

# 1. 在 settings.py 的 INSTALLED_APPS 中注册
# 2. 创建 models.py → python manage.py makemigrations → migrate
# 3. 创建 serializers.py
# 4. 创建 views.py
# 5. 创建 urls.py → 注册到 backend/urls.py
```

**新 App 最小模板**:
```python
# my_module/urls.py
app_name = 'my_module'
urlpatterns = [
    path('items/', ItemListView.as_view(), name='item-list'),
]

# backend/urls.py
urlpatterns += [
    path('api/my/', include('my_module.urls')),
]
```

## 8.2 如何新增一个前端页面

1. 在 `frontend/src/views/` 下创建 `MyPage.vue`
2. 在 `frontend/src/router/index.ts` 中添加路由:

```typescript
{
    path: '/projects/:projectId/my-page',
    component: () => import('@/views/MyPage.vue'),
    meta: { requiresAuth: true }
}
```

3. 如需 API 调用，在 `frontend/src/api/` 下创建模块:

```typescript
// frontend/src/api/mymodule.ts
import request from '@/utils/request'

export const listItems = (projectId: string) =>
    request.get(`/my/items/?project=${projectId}`)
export const createItem = (data: any) =>
    request.post('/my/items/', data)
```

## 8.3 如何新增一个 WebSocket 路由

**后端**:
```python
# my_module/consumers.py
class MyConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = f'my_{self.scope["url_route"]["kwargs"]["id"]}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
```

```python
# my_module/routing.py
websocket_urlpatterns = [
    re_path(r'ws/my/(?P<id>[^/]+)/$', MyConsumer.as_asgi()),
]

# backend/asgi.py — 添加到 URLRouter
```

**前端**:
```typescript
// composables/useMySocket.ts
export function useMySocket(id: string) {
    const ws = new WebSocket(wsHost(`/ws/my/${id}/`))
    // 复用 useWebSocket 模式
}
```

## 8.4 如何新增一个 AI 工具

在 `room/ai_utils.py` 的 `TOOLS` 字典中添加:

```python
TOOLS = [
    # ... 已有工具 ...
    {
        "type": "function",
        "function": {
            "name": "my_custom_tool",
            "description": "工具描述",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "参数说明"},
                },
                "required": ["param1"]
            }
        }
    }
]

def execute_my_custom_tool(param1, user, project):
    """实现工具逻辑"""
    # 操作数据库、调用 API 等
    return {"result": "done"}
```

然后在 `execute_tool()` 中注册处理函数:
```python
def execute_tool(tool_name, arguments, user, project):
    if tool_name == 'my_custom_tool':
        return execute_my_custom_tool(arguments['param1'], user, project)
    # ...
```

## 8.5 代码规范与最佳实践

### Python 后端
- **PEP 8** 代码风格，使用 `flake8` 检查
- **视图文件命名**: `views_<功能>.py`（如 `views_api_auto_test.py`）
- **序列化器分层**: `XxxListSerializer` / `XxxCreateSerializer` / `XxxDetailSerializer`
- **错误处理**: 使用 `backend/api_errors.py` 的统一错误函数，不要直接 `raise Exception`
- **数据库查询**: 使用 `select_related()` / `prefetch_related()` 避免 N+1

### Vue 前端
- **组件命名**: `PascalCase` 文件名、多词避免与 HTML 元素冲突
- **逻辑抽离**: 复杂逻辑放入 `composables/`，保持 `.vue` 文件简洁
- **Store 粒度**: 按业务域拆分 Store，使用聚合 Store 模式组装
- **API 调用**: 通过 `src/api/` 模块统一管理，不在组件中直接写 `axios`
- **类型安全**: 为 API 响应定义 TypeScript 接口

### Git 工作流
- **分支**: `main` (稳定) ← `dev` (开发) ← `feature/xxx` (功能)
- **提交信息**: `feat(module): 描述` / `fix(module): 描述` / `chore: 描述`
- **代码审查**: 合并到 `main` 前必须通过 PR Review

---

## 附录

### A. 关键文件索引

| 你想了解... | 去看... |
|------------|--------|
| 后端核心配置 | `backend/backend/settings.py` |
| 所有 API 路由 | `backend/room/urls.py`, `backend/qa_center/urls.py` |
| 数据模型设计 | `docs/02-数据模型.md` |
| WebSocket 详解 | `docs/03-WebSocket实时同步.md` |
| AI 工具实现 | `backend/room/ai_utils.py` |
| Bug 状态机 | `backend/bug_tracker/state_machine.py` |
| API 测试引擎 | `backend/qa_center/api_execution/` |
| 前端路由 | `frontend/src/router/index.ts` |
| WebSocket 客户端 | `frontend/src/stores/composables/useWebSocket.ts` |
| 前端样式变量 | `frontend/src/styles/variables.css` |
| Docker 部署 | `docker-compose.yml` |

### B. 学习路径建议

```
第1天: 阅读本文档 + 搭建开发环境
第2天: 理解核心数据模型 (docs/02-数据模型.md)
第3天: 理解 WebSocket 实时同步 (docs/03-WebSocket实时同步.md)
第4天: 走读 room App 源码（看板/协作/AI）
第5天: 走读 qa_center App 源码（测试/DevOps）
第6天: 走读 bug_tracker + system App 源码
第7天: 走读前端 Store + Router + Board 组件
第8天: 尝试新增一个简单功能（新字段/新页面）
```

---

> **文档版本**: v1.0  
> **最后更新**: 2026-07-04  
> **适用分支**: `dev`  
> **相关文档**: [README.md](../README.md) | [学习路线](LEARNING_ROADMAP.md) | [代码地图](CODE_MAP.md) | [技术深潜](PROJECT_DEEP_DIVE.md)
