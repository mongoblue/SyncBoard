# SyncBoard 全项目代码审查报告

**审查日期**: 2026-06-10 | **审查范围**: 全项目 (backend + frontend + infra)

---

## 问题总览

| 优先级 | 数量 | 说明 |
|--------|------|------|
| 🔴 Critical | 6 | 安全漏洞，必须立即修复 |
| 🟠 High | 9 | 功能缺陷/稳定性风险 |
| 🟡 Medium | 8 | 代码质量/维护性问题 |
| 🟢 Low | 7 | 优化建议 |

---

## 🔴 Critical — 安全漏洞

### C1. CSRF 保护被完全禁用
- **文件**: `backend/backend/authentication.py:3-5`, `backend/backend/settings.py:55`
- **问题**: `CsrfExemptSessionAuthentication` 完全跳过 CSRF 检查。`settings.py` 中 `CsrfViewMiddleware` 被注释掉。
- **风险**: 任何页面都可以伪造用户请求，配合 `ALLOWED_HOSTS=["*"]` 和 `CORS_ALLOW_CREDENTIALS=True` 构成完整的 CSRF 攻击链。
- **修复**: 启用 CSRF 中间件，移除 `CsrfExemptSessionAuthentication`，改用标准 `SessionAuthentication`。

### C2. 数据库密码硬编码在 docker-compose.yml
- **文件**: `docker-compose.yml:13`
- **问题**: `MYSQL_PASSWORD: "13579Mnb!"` 直接写在版本控制中。
- **风险**: 密码泄露到 git 历史，任何有仓库访问权限的人都能获取。
- **修复**: 使用环境变量 `${MYSQL_PASSWORD}` 引用，密码通过 `.env` 或 CI secrets 注入。

### C3. ALLOWED_HOSTS = ["*"] + DEBUG 默认值不安全
- **文件**: `backend/backend/settings.py:27-30`
- **问题**: `ALLOWED_HOSTS = ["*"]` 接受任意 Host 头；`SECRET_KEY` 有 `'unsafe-default-key'` 硬编码默认值；`DEBUG` 默认值检查失误——`os.environ.get('DEBUG', 'False') == 'True'` 只在明确设为 `True` 时才开启，但无 `.env` 时回退到不安全 key。
- **修复**: 移除 `ALLOWED_HOSTS=["*"]`，从环境变量读取；SECRET_KEY 无默认值或强制从环境变量读取，缺失则拒绝启动。

### C4. CI/CD API Token 明文存储
- **文件**: `backend/qa_center/models.py:933`
- **问题**: `CiCdConfig.api_token = models.CharField(max_length=255, blank=True)` 以明文存储 CI/CD 系统的 API token。
- **风险**: 数据库泄露 = 所有 CI/CD 系统被攻破。
- **修复**: 使用 Django 的 encrypted fields 或 Fernet 对称加密存储。

### C5. 聊天消息未做 HTML 转义 (XSS)
- **文件**: `backend/room/consumers_chat.py:89-98`
- **问题**: `ChatConsumer.chat_message` 直接广播接收到的消息内容，未调用 `sanitize_html()`。`BoardConsumer` 有 sanitize 但 `ChatConsumer` 没有。前端可能使用 `v-html` 渲染。
- **风险**: 用户可在聊天中注入 `<script>` 标签，窃取其他用户 session。
- **修复**: 在 `chat_message` 中对 `content` 进行 HTML 转义。

### C6. AI 响应在 Board.vue 中未经转义渲染
- **文件**: `frontend/src/views/Board.vue:146,157`
- **问题**: `<span v-html="highlightText(...)">` 直接渲染 HTML。`highlightText` 函数如果处理 AI 返回内容或用户输入的任务描述，存在 XSS 风险。
- **修复**: 确保 `highlightText` 在插入 `<mark>` 标签之前先对原始文本进行 HTML 转义。

---

## 🟠 High — 功能缺陷 / 稳定性风险

### H1. LogoutView 有语法错误导致登出失败
- **文件**: `backend/room/views.py:30`
- **问题**: `def post(selfself, request):` — `selfself` 是 typo，Python 会将 `request` 绑定到 `self`，导致 `request` 参数实际是 None。
- **影响**: 登出功能完全不可用。
- **修复**: 改为 `def post(self, request):`

### H2. 登出后 CSRF cookie 未清除
- **文件**: `backend/room/views.py:29-32`
- **问题**: `LogoutView` 调用 `logout(request)` 后没有清除 CSRF token cookie，客户端可能继续使用过期凭证。
- **修复**: `logout(request)` 后返回带有 `Set-Cookie` 清除 csrftoken 头的响应。

### H3. 广播函数异常处理不完整
- **文件**: `backend/room/views.py:55-66`
- **问题**: `broadcast_task_change` 中若 `task_instance.column.project.id` 抛出 `AttributeError`，只打印警告后静默返回。删除操作的 `TempTask` 结构脆弱——若 Task 模型增加必填字段会直接崩溃。
- **修复**: 在 delete 前提取 `project_id`，传递给 `broadcast_task_change`。

### H4. AI 端点无速率限制
- **文件**: `backend/room/urls.py:85-95`, `backend/room/views.py:407-495`
- **问题**: 7 个 AI 相关端点使用 `permissions.IsAuthenticated` 但没有任何 throttling。每次 AI 调用消耗 API 费用和服务器资源。
- **修复**: 为 AI 端点添加专用 throttle class（如 20/min per user）。

### H5. 性能测试 locustfile 使用硬编码凭证
- **文件**: `backend/performance/locustfile.py:12-13`
- **问题**: `username = "test_user"`, `password = "password123"` 硬编码，CI 中可能没有此用户导致 locust 测试全部失败。
- **修复**: 从环境变量读取。

### H6. Notification 保存时对每个活跃用户都创建记录
- **文件**: `backend/room/consumers_global.py:41-56`
- **问题**: `GlobalConsumer.save_notification` 对 `User.objects.filter(is_active=True)` 每个用户创建一条 Notification。用户量增长时，一条系统通知会产生 N 次 DB 写入。
- **修复**: 使用 `bulk_create` 或者按需推送（不在数据库存储广播通知）。

### H7. RunTestView 的 subprocess 命令注入风险
- **文件**: `backend/qa_center/views.py:72-104`
- **问题**: `test_type` 来自 `request.data`，虽然用 dict 映射限制了路径，但如果新增类型未正确限制，可能导致命令注入。
- **当前状态**: 使用了 dict 映射，路径基本安全。但 `python_exec = sys.executable` 如果在虚拟环境中路径包含空格可能出错。
- **修复**: 使用列表形式的 cmd（已在做），确保所有路径经过验证。

### H8. ChatConsumer Redis 连接在模块级别创建
- **文件**: `backend/room/consumers_chat.py:10`
- **问题**: `r = redis.Redis(...)` 在模块导入时创建连接。如果 Redis 不可用，整个模块导入失败，Django 无法启动。
- **修复**: 延迟初始化或在 `connect()` 中创建连接。

### H9. NotificationListView 分页是伪分页
- **文件**: `backend/room/views.py:504-539`
- **问题**: 先 `.count()` 查全量，然后 Python 切片 `[start:end]`。Django 的 QuerySet 切片会转为 SQL LIMIT/OFFSET，但不必要的 `.count()` 额外查询。且序列化用 for 循环而非 Serializer，失去验证和字段控制。
- **修复**: 使用 DRF 的 `PageNumberPagination` 或 `LimitOffsetPagination`。

---

## 🟡 Medium — 代码质量 / 维护性

### M1. ProjectListView.delete 路由混淆
- **文件**: `backend/room/urls.py:78`, `backend/room/views.py:369`
- **问题**: `path('projects/<str:pk>/', ProjectListView.as_view())` 将 GET/POST(列表) 和 DELETE(详情) 混在同一视图。`ProjectListView.delete(self, request, pk)` 接收 `pk` 但 URL pattern 已提供——Django 的 `APIView` 默认不传递 URL kwargs 到 delete，所以 `pk` 参数不会自动填充。
- **修复**: 分离为 `ProjectDetailView`。

### M2. .env 文件不应在仓库中
- **文件**: `backend/.env`
- **问题**: `.env` 文件存在并可能包含真实密钥。`.gitignore` 中有 `.env` 规则，但文件可能已被追踪。
- **修复**: `git rm --cached backend/.env` 确保不再追踪。

### M3. 大量无用的临时文件被追踪
- **文件**: `.docker-compose.swp`, `backend/test_output_*.csv`, `backend/debug_before_click.png`, `backend/login_success.png`, 根目录的 `login_success.png`, `task_create_success.png`, `package-lock.json`
- **问题**: Vim 交换文件、调试截图、测试输出 CSV 被 git 追踪或存在于工作区。
- **修复**: 清理这些文件并确保 `.gitignore` 规则覆盖。

### M4. 调试打印语句散布在代码中
- **文件**: 多处 (`room/views.py:98,176`, `room/consumers_global.py:20,56,57`, `consumers_chat.py:57`, etc.)
- **问题**: 生产代码中大量 `print()` 语句。应该使用 `logging` 模块。
- **修复**: 替换为 `logger.info()` / `logger.debug()`。

### M5. Celery tasks 中的 bare except
- **文件**: `backend/backend/tasks.py:19,24,36`
- **问题**: `except Exception: pass` 和 `except Exception as e: print(...)` 吞掉所有错误。ES 索引更新失败时静默丢失。
- **修复**: 至少记录到 logger，考虑 Sentry/重试机制。

### M6. 前端 API 请求无统一错误处理
- **文件**: `frontend/src/utils/request.ts:36-65`
- **问题**: 404 静默处理，500 只打印日志。未登录（401）不触发重新登录。网络错误无用户提示。
- **修复**: 401 时自动跳转登录页；使用 ElMessage 显示网络错误。

### M7. TypeScript 类型使用 `any` 过多
- **文件**: `frontend/src/stores/Auth.ts:48`, `frontend/src/views/Board.vue:289`
- **问题**: `login(form: any)`, `boardStore.Columns` 未类型化，任务对象使用 `any`。
- **修复**: 定义明确的接口类型。

### M8. LogoutView 问题 + 前端 Auth store 无 logout 错误处理
- **文件**: `frontend/src/stores/Auth.ts:93-99`
- **问题**: `logout` 失败时 `user` 仍被设为 `null`，用户看起来登出了但服务端 session 未清除。
- **修复**: 加 try-catch，失败时保留 user 状态。

---

## 🟢 Low — 优化建议

### L1. 无健康检查端点
- 建议: 添加 `/api/health/` 返回 200，供负载均衡器和 CI 使用（CI 中 `load-test` job 引用了 `/health` 但路由未定义）。

### L2. Django Admin 未保护
- 建议: 为 `/admin/` 添加 IP 白名单或额外认证。

### L3. Celery worker 缺少健康检查
- 建议: docker-compose 中 `celery_worker` 服务缺少 healthcheck。

### L4. 前端 global.css 文件被引用但未确认存在
- **文件**: `frontend/src/main.ts:7`
- 检查 `frontend/src/styles/global.css` 是否存在。

### L5. `package-lock.json` 在项目根目录
- 文件只有 94 字节，可能是意外生成的。应删除。

### L6. README.md 和 API 文档需更新
- README.md 很大 (~16KB)，但可能包含过时信息。

### L7. whoosh_cn_backend.py 属于死代码
- settings.py 中未配置 Whoosh 后端，使用 ES 后端。

---

## 修复优先级排序

按风险 × 修复成本排序：

1. **C1** CSRF 保护恢复 — 中等成本，极高风险
2. **C5 + C6** XSS 修复 — 低到中等成本，高风险
3. **H1** Logout 语法错误 — 极低成本，功能完全不可用
4. **C2** 移除硬编码密码 — 低成本，中等风险
5. **C3** ALLOWED_HOSTS 收紧 — 低成本
6. **H4** AI 端点限流 — 低成本
7. **H3** 广播异常处理 — 中等成本
8. **H5** Locust 环境变量 — 低成本
9. **H6** Notification 批量创建 — 低成本
10. **其余** — 逐个处理
