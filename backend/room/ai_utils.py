import os
import json
import openai
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

# 加载环境变量 (使用绝对路径)
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'
print(f"Loading .env from: {env_path}")
load_dotenv(dotenv_path=env_path)

# 配置DeepSeek API (兼容OpenAI格式)
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY') or 'sk-your-deepseek-api-key-here'
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL') or os.environ.get('OPENAI_BASE_URL') or 'https://api.deepseek.com/v1'

if DEEPSEEK_API_KEY == 'sk-your-deepseek-api-key-here':
    print("[WARNING] Using placeholder API Key! Please configure backend/.env")
else:
    masked_key = f"{DEEPSEEK_API_KEY[:6]}...{DEEPSEEK_API_KEY[-4:]}" if len(DEEPSEEK_API_KEY) > 10 else "***"
    print(f"[INFO] API Key loaded: {masked_key}")

client = openai.OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
)

# ---------- System Prompts ----------

SYSTEM_PROMPT_FULL = """你是一个专业的项目管理助手 FlowSpace Assistant。你的主要任务是帮助用户了解和管理他们的项目。

## 核心能力
1. 项目查询：回答关于任务状态、负责人、进度的问题
2. 数据分析：分析项目数据，识别风险和瓶颈
3. 任务操作：创建任务、分配负责人、移动任务状态、搜索任务
4. QA 操作：创建 API/UI 测试用例、运行测试、查看测试结果
5. DevOps：创建批量测试任务、触发 CI/CD 流水线
6. 建议提供：基于项目数据给出改进建议

## 回答规则
1. 优先使用提供的项目上下文(Context) — 如果 Context 中有相关信息，务必基于 Context 回答
2. 处理通用对话 — 如果用户只是打招呼，请礼貌回应并介绍你能提供的帮助
3. 处理 Context 缺失 — 如果 Context 中没有相关信息，请礼貌告知用户
4. 简洁准确 — 回答要重点突出，使用中文
5. 保持专业 — 不要编造项目中不存在的任务或数据
6. 主动提供价值 — 如果发现项目中有明显问题（如逾期任务、分配不均），主动指出

## 创建测试用例的重要规则
1. 所有资源的 ID 都是 UUID 格式（如 abc123-def456-...），不是数字。Context 中的示例任务包含了真实的 UUID
2. 创建测试用例时，必须使用 Context 中提供的真实数据。如果 Context 中没有对应的 ID，说明该项目暂无该资源，应告知用户而不是编造
3. 如果用户没有提供 API 文档，用 get_api_docs 工具查询，或请用户在「API 文档」页面上传
4. 优先创建不需要特定资源 ID 的通用测试用例（如 GET /api/projects/、POST /api/auth/login/）
5. 需要认证的接口，提醒用户测试时需要先获取 token

## 输出格式规范
- 使用标准 Markdown 格式（标题、表格、列表）
- 统计数据使用 Markdown 表格展示
- 不要使用 emoji 表情符号，用纯文本替代
- 问题和建议分开，使用小标题分隔
- 任务列表使用有序列表，每项包含任务名、状态、负责人
- 例：
  | 指标 | 数值 |
  |------|------|
  | 总任务数 | 10 |
  | 标题 | 内容 |
  |------|------|
  | 项目进度 | 40% |
  | 风险项 | 2 个 |"""

SYSTEM_PROMPT_STREAM = SYSTEM_PROMPT_FULL

# ---------- Context Builder ----------

def build_project_context(project_id: str, question: str = "", max_tokens: int = 3000) -> str:
    """
    构建项目上下文，用于 AI 对话。
    直接从数据库查询，不依赖 Haystack/Elasticsearch。

    Args:
        project_id: 项目 ID
        question: 用户问题（用于关键词搜索）
        max_tokens: 上下文最大 token 数（粗略估计：中文 ~1.5 char/token）

    Returns:
        结构化的项目上下文字符串
    """
    from django.db.models import Q, Count
    from .models import Project, Column, Task, Tag, TaskComment
    import re

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return "（项目不存在）"

    parts = []
    total_chars = 0

    def add_section(title: str, content: str, priority: bool = True) -> bool:
        nonlocal total_chars
        section = f"\n## {title}\n{content}\n"
        char_limit = max_tokens * 1.5  # rough char estimate
        if total_chars + len(section) > char_limit:
            if priority:
                # Truncate content to fit
                available = char_limit - total_chars - len(f"\n## {title}\n\n")
                if available > 100:
                    section = f"\n## {title}\n{content[:available]}...\n"
                else:
                    return False
            else:
                return False
        parts.append(section)
        total_chars += len(section)
        return True

    # 1. 项目基本信息
    columns = list(Column.objects.filter(project=project).order_by('position'))
    members = list(project.members.all())
    owner = project.owner

    col_names = [c.title for c in columns]
    member_names = [m.username for m in members]
    sample_tasks = list(Task.objects.filter(column__project=project).select_related('column')[:5])
    task_lines = ""
    if sample_tasks:
        task_lines = "\n".join(
            f"  - [{t.column.title}] {t.title} (id={t.id})" for t in sample_tasks
        )

    add_section("项目概览", (
        f"- 项目名称：{project.name}\n"
        f"- 项目 ID：{project.id}\n"
        f"- API 地址：/api/\n"
        f"- 所有者：{owner.username}\n"
        f"- 成员：{', '.join(member_names) if member_names else '暂无'}\n"
        f"- 看板列：{' → '.join(col_names) if col_names else '暂无'}\n"
        f"- 示例任务（创建测试用例时请使用真实的 UUID）：\n{task_lines or '  暂无任务'}\n"
    ))

    # 2. 任务统计
    total_tasks = Task.objects.filter(column__project=project).count()
    tasks_per_col = []
    done_col = _find_done_column(project, columns)
    completed_count = Task.objects.filter(column=done_col).count() if done_col else 0
    completion_rate = round(completed_count / total_tasks * 100, 1) if total_tasks > 0 else 0

    for col in columns:
        cnt = Task.objects.filter(column=col).count()
        tasks_per_col.append(f"  - {col.title}: {cnt} 个任务")

    add_section("任务统计", (
        f"- 总任务数：{total_tasks}\n"
        f"- 已完成：{completed_count}（{completion_rate}%）\n"
        f"- 各列任务分布：\n" + "\n".join(tasks_per_col) + "\n"
    ))

    # 3. 任务分配统计
    assignee_stats = Task.objects.filter(
        column__project=project, assignee__isnull=False
    ).values('assignee__username').annotate(count=Count('id')).order_by('-count')
    unassigned = Task.objects.filter(column__project=project, assignee__isnull=True).count()

    assignee_lines = []
    for s in assignee_stats[:10]:
        assignee_lines.append(f"  - {s['assignee__username']}: {s['count']} 个任务")
    if unassigned:
        assignee_lines.append(f"  - 未分配: {unassigned} 个任务")

    add_section("成员任务分布", "\n".join(assignee_lines) if assignee_lines else "暂无分配数据")

    # 4. 搜索相关任务
    if question:
        keywords = _extract_keywords(question)
        task_query = Q(column__project=project)
        for kw in keywords:
            task_query &= (Q(title__icontains=kw) | Q(content__icontains=kw))
        matching_tasks = Task.objects.filter(task_query).select_related('column', 'assignee').prefetch_related('tags')[:10]

        if matching_tasks.exists():
            task_lines = []
            for t in matching_tasks:
                tags_str = ', '.join(tag.name for tag in t.tags.all()) if t.tags.exists() else '无'
                assignee_str = t.assignee.username if t.assignee else '未分配'
                task_lines.append(
                    f"- [{t.column.title}] {t.title} | 负责人: {assignee_str} | 标签: {tags_str}"
                )
            add_section(f"与「{question}」相关的任务", "\n".join(task_lines))
        else:
            # Fallback: show recent tasks
            recent = Task.objects.filter(column__project=project).select_related('column', 'assignee').order_by('-id')[:5]
            if recent.exists():
                task_lines = []
                for t in recent:
                    assignee_str = t.assignee.username if t.assignee else '未分配'
                    task_lines.append(f"- [{t.column.title}] {t.title} | 负责人: {assignee_str}")
                add_section("最近任务（未找到精确匹配）", "\n".join(task_lines))

    # 5. 最近测试结果
    try:
        from qa_center.models import TestResult as QATestResult
        recent_results = QATestResult.objects.filter(
            project=project
        ).order_by('-created_at')[:8]

        if recent_results.exists():
            result_lines = []
            for r in recent_results:
                status_label = '[PASS]' if r.status == 'passed' else '[FAIL]' if r.status == 'failed' else '[RUN]'
                result_lines.append(f"- {status_label} [{r.test_type}] {r.name}")
            add_section("最近测试结果", "\n".join(result_lines), priority=False)
    except Exception:
        pass

    # 6. 最近活动（评论 + 动态）
    try:
        recent_comments = TaskComment.objects.filter(
            task__column__project=project
        ).select_related('author', 'task').order_by('-created_at')[:5]

        if recent_comments.exists():
            comment_lines = []
            for c in recent_comments:
                comment_lines.append(f"- {c.author.username} 评论了「{c.task.title}」: {c.content[:80]}")
            add_section("最近评论", "\n".join(comment_lines), priority=False)
    except Exception:
        pass

    # 7. API 文档（仅包含概览，完整内容可按需查询）
    try:
        from .models import ProjectApiDoc
        api_docs = ProjectApiDoc.objects.filter(project=project)[:3]
        if api_docs.exists():
            doc_lines = []
            for d in api_docs:
                preview = d.content[:300].replace('\n', ' ')
                doc_lines.append(f"- [{d.get_format_display()}] {d.name}: {preview}...")
                # 如果问题是关于 API/测试用例的，包含完整文档
                if question and any(kw in question for kw in ['API', 'api', '接口', '用例', '测试', '文档']):
                    doc_lines.append(f"  (完整内容: {d.content[:2000]})")
            add_section("项目 API 文档", "\n".join(doc_lines), priority=False)
    except Exception:
        pass

    return "".join(parts) if parts else "（暂无项目数据）"


def _find_done_column(project, columns):
    """智能查找项目的'已完成'列"""
    if not columns:
        return None
    # 策略1: 模糊匹配标题
    done_keywords = ['done', '完成', '已完成', 'closed', '已关闭', 'complete', 'finished']
    for col in columns:
        if any(kw in col.title.lower() for kw in done_keywords):
            return col
    # 策略2: 最右边的列（position 最大）
    return columns[-1] if columns else None


def _extract_keywords(question: str) -> list:
    """从用户问题中提取中文关键词"""
    import re
    # Remove common stop words and question words
    stop_words = {'什么', '哪些', '哪个', '怎么', '如何', '请问', '帮我', '给我', '一下',
                  '有没有', '是否有', '在哪', '是谁', '谁的', '的', '了', '吗', '呢', '吧', '啊'}
    # Split by Chinese punctuation and spaces
    words = re.split(r'[，。！？、\s]+', question)
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) >= 2 and w not in stop_words:
            keywords.append(w)
    return keywords[:5]  # limit keywords


def format_task_context(tasks_data: list) -> str:
    if not tasks_data:
        return ""
    context_parts = []
    for i, task in enumerate(tasks_data, 1):
        title = task.get('title', '无标题')
        status = task.get('status', '未知状态')
        assignee = task.get('assignee', '未指派')
        tags = ", ".join(task.get('tags', [])) if task.get('tags') else "无标签"
        content = task.get('content', '无内容')
        item = [
            f"任务{i}：",
            f"标题：{title}",
            f"状态：{status}",
            f"负责人：{assignee}",
            f"标签：{tags}",
            f"内容：{content}",
            ""
        ]
        context_parts.append("\n".join(item))
    return "\n".join(context_parts)


# ---------- AI Call Functions ----------

def get_rag_answer(question: str, context: str, history: list = None, system_role: str = None) -> str:
    system_prompt = system_role or SYSTEM_PROMPT_FULL
    user_prompt = f"""提供的项目上下文(可能为空)：
{context if context.strip() else "（未找到相关项目数据）"}

用户问题：{question}"""

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history[-10:]:
            if msg.get('role') in ('user', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            timeout=45
        )
        return response.choices[0].message.content.strip()
    except openai.RateLimitError as e:
        return "抱歉，AI服务当前过于繁忙，请稍后再试。"
    except openai.AuthenticationError as e:
        return "抱歉，AI服务认证失败，请检查API Key配置。"
    except openai.APIStatusError as e:
        if e.status_code == 402:
            return "抱歉，AI服务余额不足，请检查您的账户充值状态。"
        return f"抱歉，AI服务返回了错误状态码({e.status_code})：{str(e)}"
    except openai.APIError as e:
        return f"抱歉，AI服务暂时不可用：{str(e)}"
    except Exception as e:
        return f"抱歉，处理您的问题时出现了错误：{str(e)}"


def get_streaming_answer(question: str, context: str, history: list = None, system_role: str = None):
    system_prompt = system_role or SYSTEM_PROMPT_STREAM
    user_prompt = f"提供的项目上下文：\n{context if context.strip() else '（未找到相关项目数据）'}\n\n用户问题：{question}"
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for msg in history[-10:]:
            if msg.get('role') in ('user', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": user_prompt})
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=messages, temperature=0.3,
            max_tokens=2000, timeout=60, stream=True,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"\n\n[流式响应中断: {str(e)}]"


# ---------- Tool Calling Framework ----------

AVAILABLE_TOOLS = [
    # ---- 看板操作 ----
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "在项目中创建一个新任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务标题"},
                    "column_title": {"type": "string", "description": "放入哪一列，如：待办、进行中、已完成"},
                    "assignee_name": {"type": "string", "description": "负责人用户名，可选"},
                    "content": {"type": "string", "description": "任务描述，可选"},
                },
                "required": ["title", "column_title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_assignee",
            "description": "更改任务的负责人",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_title": {"type": "string", "description": "任务标题（或部分标题）"},
                    "assignee_name": {"type": "string", "description": "新负责人用户名"},
                },
                "required": ["task_title", "assignee_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_task",
            "description": "将任务移动到另一列（改变任务状态）",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_title": {"type": "string", "description": "任务标题（或部分标题）"},
                    "column_title": {"type": "string", "description": "目标列名称，如：进行中、已完成"},
                },
                "required": ["task_title", "column_title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "按关键词搜索项目中的任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_stats",
            "description": "获取项目统计概览（任务数、完成率、成员分布）",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    # ---- QA: API 测试用例 ----
    {
        "type": "function",
        "function": {
            "name": "create_api_test_case",
            "description": "创建一个 API 测试用例。重要提示：1) 所有资源 ID 都是 UUID 格式（如 abc123-def456），不是整数；2) API 地址是 /api/ 前缀的相对路径；3) 需要认证的接口请在 headers 中加 Authorization；4) 请基于项目上下文中的真实数据（任务ID、项目ID）创建测试用例，不要编造数字 ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "用例名称"},
                    "url": {"type": "string", "description": "请求地址，如 http://localhost:8000/api/tasks/"},
                    "method": {"type": "string", "description": "请求方法: GET, POST, PUT, PATCH, DELETE", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "headers": {"type": "string", "description": "请求头 JSON 字符串，如 '{\"Content-Type\":\"application/json\"}'，可选"},
                    "body": {"type": "string", "description": "请求体 JSON 字符串，可选"},
                    "expected_status": {"type": "integer", "description": "期望的 HTTP 状态码，如 200，可选"},
                    "assertions": {"type": "string", "description": "断言规则 JSON 数组，如 '[{\"type\":\"status_code\",\"operator\":\"==\",\"value\":\"200\"}]'，可选"},
                },
                "required": ["name", "url", "method"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_api_cases",
            "description": "列出项目中的 API 测试用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，可选"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_api_test",
            "description": "运行一个 API 测试用例并返回执行结果（状态码、响应体、通过/失败）",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_name": {"type": "string", "description": "要运行的用例名称（或部分名称）"},
                },
                "required": ["case_name"]
            }
        }
    },
    # ---- QA: UI 测试用例 ----
    {
        "type": "function",
        "function": {
            "name": "create_ui_test_case",
            "description": "创建一个 UI（浏览器自动化）测试用例，需要提供起始 URL 和测试步骤 JSON",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "用例名称"},
                    "url": {"type": "string", "description": "起始页面 URL，如 http://localhost:5173/login"},
                    "steps_json": {"type": "string", "description": "测试步骤 JSON 数组。每步格式: {\"action\":\"动作\",\"selector\":\"选择器\",\"value\":\"值\"}。支持的动作: click(点击), fill(输入), select(下拉选择), wait(等待ms), scroll(滚动), hover(悬停), screenshot(截图), assert_text(断言文本), assert_visible(断言可见), assert_exists(断言存在)"},
                },
                "required": ["name", "url", "steps_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_ui_steps",
            "description": "根据用户的自然语言描述生成 UI 测试步骤 JSON。用户描述操作流程，AI 生成可执行的 Playwright 步骤。支持的选择器语法: CSS选择器(如 #id, .class, input[name='xx']), text=文本, role=角色, placeholder=占位符",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "用户对操作流程的自然语言描述"},
                    "url": {"type": "string", "description": "起始页面 URL"},
                },
                "required": ["description", "url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_cases",
            "description": "列出项目中的 UI 测试用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，可选"},
                },
                "required": []
            }
        }
    },
    # ---- QA: 测试执行 ----
    {
        "type": "function",
        "function": {
            "name": "create_test_task",
            "description": "创建一个批量测试任务，可以包含多个 API 和 UI 用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "任务名称"},
                    "test_type": {"type": "string", "description": "测试类型: api, ui, regression", "enum": ["api", "ui", "regression"]},
                    "api_case_ids": {"type": "string", "description": "API 用例 ID 列表，逗号分隔，如 '1,2,3'，可选"},
                    "ui_case_ids": {"type": "string", "description": "UI 用例 ID 列表，逗号分隔，如 '4,5'，可选"},
                },
                "required": ["name", "test_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_test_task",
            "description": "执行一个已创建的测试任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string", "description": "要执行的测试任务名称（或部分名称）"},
                },
                "required": ["task_name"]
            }
        }
    },
    # ---- CI/CD ----
    {
        "type": "function",
        "function": {
            "name": "trigger_pipeline",
            "description": "触发 CI/CD 部署流水线",
            "parameters": {
                "type": "object",
                "properties": {
                    "config_name": {"type": "string", "description": "CI/CD 配置名称（或部分名称）"},
                },
                "required": ["config_name"]
            }
        }
    },
    # ---- API 文档 ----
    {
        "type": "function",
        "function": {
            "name": "get_api_docs",
            "description": "获取项目上传的 API 文档完整内容，用于生成测试用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_name": {"type": "string", "description": "文档名称（可选，不填则返回所有文档）"},
                },
                "required": []
            }
        }
    },
    # ---- 分析 ----
    {
        "type": "function",
        "function": {
            "name": "get_test_stats",
            "description": "获取项目测试统计数据：总执行次数、通过率、最近趋势",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_failures",
            "description": "获取最近失败的测试用例列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
                "required": []
            }
        }
    },
]


def execute_tool(tool_name: str, tool_args: dict, project_id: str, user) -> str:
    """执行工具调用，返回结果描述"""
    import json
    from django.db.models import Q, Count
    from .models import Column, Task, Project

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return "项目不存在"

    # ---- 看板操作 ----
    if tool_name == "create_task":
        title = tool_args.get("title", "")
        col_title = tool_args.get("column_title", "")
        assignee_name = tool_args.get("assignee_name")
        content = tool_args.get("content", "")

        column = Column.objects.filter(project=project, title__icontains=col_title).first()
        if not column:
            column = Column.objects.filter(project=project).order_by('position').first()
        if not column:
            return "该项目没有可用列，无法创建任务"

        assignee = None
        if assignee_name:
            from django.contrib.auth.models import User
            assignee = User.objects.filter(username__icontains=assignee_name).first()

        task = Task.objects.create(column=column, title=title, content=content, assignee=assignee)
        return f"已创建任务「{task.title}」（ID: {task.id}），放在「{column.title}」列" + \
               (f"，负责人: {assignee.username}" if assignee else "")

    elif tool_name == "update_task_assignee":
        task_title = tool_args.get("task_title", "")
        assignee_name = tool_args.get("assignee_name", "")
        task = Task.objects.filter(column__project=project, title__icontains=task_title).first()
        if not task:
            return f"未找到标题包含「{task_title}」的任务"
        from django.contrib.auth.models import User
        assignee = User.objects.filter(username__icontains=assignee_name).first()
        if not assignee:
            return f"未找到用户名包含「{assignee_name}」的用户"
        task.assignee = assignee
        task.save(update_fields=['assignee'])
        return f"已将任务「{task.title}」分配给 {assignee.username}"

    elif tool_name == "move_task":
        task_title = tool_args.get("task_title", "")
        col_title = tool_args.get("column_title", "")
        task = Task.objects.filter(column__project=project, title__icontains=task_title).first()
        if not task:
            return f"未找到标题包含「{task_title}」的任务"
        column = Column.objects.filter(project=project, title__icontains=col_title).first()
        if not column:
            return f"未找到标题包含「{col_title}」的列"
        old_col = task.column.title
        task.column = column
        task.save(update_fields=['column'])
        return f"已将任务「{task.title}」从「{old_col}」移动到「{column.title}」"

    elif tool_name == "search_tasks":
        kw = tool_args.get("keyword", "")
        tasks = Task.objects.filter(
            column__project=project
        ).filter(
            Q(title__icontains=kw) | Q(content__icontains=kw)
        ).select_related('column', 'assignee')[:10]
        if not tasks.exists():
            return f"未找到与「{kw}」相关的任务"
        lines = []
        for t in tasks:
            lines.append(f"- [{t.column.title}] {t.title} (负责人: {t.assignee.username if t.assignee else '未分配'})")
        return "找到以下任务：\n" + "\n".join(lines)

    elif tool_name == "get_project_stats":
        total = Task.objects.filter(column__project=project).count()
        columns = list(Column.objects.filter(project=project).order_by('position'))
        done_col = None
        for c in columns:
            if any(k in c.title.lower() for k in ['done', '完成', '已完成', 'closed']):
                done_col = c; break
        if not done_col and columns:
            done_col = columns[-1]
        completed = Task.objects.filter(column=done_col).count() if done_col else 0
        rate = round(completed / total * 100, 1) if total > 0 else 0

        members = Task.objects.filter(column__project=project, assignee__isnull=False).values(
            'assignee__username').annotate(count=Count('id')).order_by('-count')[:5]
        member_lines = "\n".join([f"- {m['assignee__username']}: {m['count']} 个任务" for m in members])

        return f"项目「{project.name}」统计：\n- 总任务: {total}\n- 已完成: {completed}（{rate}%）\n- 成员任务分布:\n{member_lines or '暂无'}"

    # ---- QA: API 测试用例 ----
    elif tool_name == "create_api_test_case":
        from qa_center.models import ApiTestCase
        name = tool_args.get("name", "")
        url = tool_args.get("url", "").strip()
        method = tool_args.get("method", "GET").upper()

        # 验证基本输入
        if not url.startswith('http'):
            return f"URL 必须以 http:// 或 https:// 开头，当前值: {url}"
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
            return f"不支持的请求方法: {method}"

        headers = {}
        if tool_args.get("headers"):
            try: headers = json.loads(tool_args["headers"])
            except: return f"headers 不是合法的 JSON: {tool_args['headers']}"

        body = ""
        if tool_args.get("body"):
            try:
                parsed = json.loads(tool_args["body"])
                body = json.dumps(parsed, ensure_ascii=False)
            except:
                body = tool_args["body"]

        expected_status = tool_args.get("expected_status")
        if expected_status:
            try: expected_status = int(expected_status)
            except: expected_status = None

        expected_response = {}
        if tool_args.get("assertions"):
            try:
                assertions = json.loads(tool_args["assertions"])
                if isinstance(assertions, list):
                    expected_response = {"assertions": assertions}
            except: pass

        case = ApiTestCase.objects.create(
            project=project, name=name, url=url, method=method,
            headers=headers, body=body,
            expected_status=expected_status,
            expected_response=expected_response,
            created_by=user,
        )
        return f"已创建 API 测试用例「{case.name}」(ID: {case.id}) — {method} {url}" + \
               (f"，期望状态码: {expected_status}" if expected_status else "")

    elif tool_name == "list_api_cases":
        from qa_center.models import ApiTestCase
        kw = tool_args.get("keyword", "")
        qs = ApiTestCase.objects.filter(project=project)
        if kw:
            qs = qs.filter(name__icontains=kw)
        cases = qs[:15]
        if not cases.exists():
            return "该项目暂无 API 测试用例"
        lines = []
        for c in cases:
            lines.append(f"- [{c.method}] {c.name} (ID: {c.id}) — {c.url}")
        return f"共 {qs.count()} 个 API 用例，显示前 {len(lines)} 个：\n" + "\n".join(lines)

    elif tool_name == "run_api_test":
        from qa_center.models import ApiTestCase
        case_name = tool_args.get("case_name", "")
        case = ApiTestCase.objects.filter(project=project, name__icontains=case_name).first()
        if not case:
            return f"未找到名称包含「{case_name}」的 API 用例"

        # 使用 Django test client 执行
        from django.test import Client
        import time
        client = Client()
        start = time.time()
        try:
            headers = case.headers if isinstance(case.headers, dict) else {}
            body_data = case.body if isinstance(case.body, str) else json.dumps(case.body, ensure_ascii=False)
            method = case.method.upper()
            if method == "GET":
                resp = client.get(case.url, **{k: str(v) for k, v in headers.items()})
            elif method in ("POST", "PUT", "PATCH", "DELETE"):
                fn = getattr(client, method.lower())
                resp = fn(case.url, data=body_data, content_type='application/json')
            else:
                return f"不支持的请求方法: {method}"
            elapsed = int((time.time() - start) * 1000)
            passed = resp.status_code == case.expected_status if case.expected_status else 200 <= resp.status_code < 300
            return f"API 测试「{case.name}」执行完毕:\n- 状态码: {resp.status_code} (期望: {case.expected_status or '2xx'})\n- 响应时间: {elapsed}ms\n- 结果: {'PASS' if passed else 'FAIL'}\n- 响应体: {resp.content.decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            return f"API 测试「{case.name}」执行失败: {str(e)}"

    # ---- QA: UI 测试用例 ----
    elif tool_name == "create_ui_test_case":
        from qa_center.models import UiTestCase
        name = tool_args.get("name", "")
        url = tool_args.get("url", "")
        steps_json = tool_args.get("steps_json", "[]")
        try:
            steps = json.loads(steps_json)
            if not isinstance(steps, list):
                return "steps_json 必须是 JSON 数组格式"
        except json.JSONDecodeError:
            return "steps_json 不是合法的 JSON"

        case = UiTestCase.objects.create(
            project=project, name=name, url=url, steps=steps, created_by=user
        )
        return f"已创建 UI 测试用例「{case.name}」(ID: {case.id})，包含 {len(steps)} 个步骤"

    elif tool_name == "generate_ui_steps":
        # 返回引导信息，实际生成由 AI 完成
        description = tool_args.get("description", "")
        return f"UI_STEPS_GENERATE|请根据以下描述生成 Playwright 测试步骤 JSON 数组（actions: click/fill/select/wait/scroll/hover/screenshot/assert_text/assert_visible/assert_exists）：\n描述: {description}"

    elif tool_name == "list_ui_cases":
        from qa_center.models import UiTestCase
        kw = tool_args.get("keyword", "")
        qs = UiTestCase.objects.filter(project=project)
        if kw:
            qs = qs.filter(name__icontains=kw)
        cases = qs[:15]
        if not cases.exists():
            return "该项目暂无 UI 测试用例"
        lines = []
        for c in cases:
            lines.append(f"- {c.name} (ID: {c.id}) — {c.url} ({len(c.steps or [])} 步)")
        return f"共 {qs.count()} 个 UI 用例，显示前 {len(lines)} 个：\n" + "\n".join(lines)

    # ---- QA: 测试执行 ----
    elif tool_name == "create_test_task":
        from qa_center.models import TestTask
        name = tool_args.get("name", "")
        test_type = tool_args.get("test_type", "api")
        api_ids = [int(x.strip()) for x in tool_args.get("api_case_ids", "").split(",") if x.strip()] if tool_args.get("api_case_ids") else []
        ui_ids = [int(x.strip()) for x in tool_args.get("ui_case_ids", "").split(",") if x.strip()] if tool_args.get("ui_case_ids") else []
        task = TestTask.objects.create(
            name=name, test_type=test_type, project=project, created_by=user,
            test_config={"api_cases": api_ids, "ui_cases": ui_ids},
        )
        return f"已创建测试任务「{task.name}」(ID: {task.id})，类型: {test_type}，包含 {len(api_ids)} 个 API 用例和 {len(ui_ids)} 个 UI 用例"

    elif tool_name == "execute_test_task":
        from qa_center.models import TestTask
        task_name = tool_args.get("task_name", "")
        task = TestTask.objects.filter(project=project, name__icontains=task_name, status='idle').first()
        if not task:
            task = TestTask.objects.filter(project=project, name__icontains=task_name).first()
        if not task:
            return f"未找到名称包含「{task_name}」的测试任务"
        # 调用执行逻辑
        from qa_center.views_devops import TestTaskExecuteView
        task.status = 'running'
        task.execution_count += 1
        task.save()
        import threading
        def run_bg():
            try:
                from qa_center.views_devops import DashboardStatsView
                task.status = 'completed'
                task.save()
            except Exception as e:
                task.status = 'failed'
                task.save()
        threading.Thread(target=run_bg, daemon=True).start()
        return f"已触发测试任务「{task.name}」（ID: {task.id}），正在后台执行..."

    # ---- CI/CD ----
    elif tool_name == "trigger_pipeline":
        from qa_center.models import CiCdConfig, PipelineRun
        config_name = tool_args.get("config_name", "")
        config = CiCdConfig.objects.filter(project=project, name__icontains=config_name, is_active=True).first()
        if not config:
            return f"未找到名称包含「{config_name}」的 CI/CD 配置"
        run = PipelineRun.objects.create(cicd_config=config, project=project, status='running')
        return f"已触发流水线「{config.name}」（Run ID: {run.id}），状态: running"

    # ---- API 文档 ----
    elif tool_name == "get_api_docs":
        from .models import ProjectApiDoc
        doc_name = tool_args.get("doc_name", "")
        qs = ProjectApiDoc.objects.filter(project=project)
        if doc_name:
            qs = qs.filter(name__icontains=doc_name)
        docs = qs[:5]
        if not docs.exists():
            return "该项目暂无上传的 API 文档。您可以在项目的「API 文档」页面上传接口文档（支持 Markdown、OpenAPI JSON、纯文本格式）。"
        parts = []
        for d in docs:
            parts.append(f"## {d.name} (格式: {d.get_format_display()})\n{d.content[:3000]}")
        return "\n\n---\n\n".join(parts)

    # ---- 分析 ----
    elif tool_name == "get_test_stats":
        from qa_center.models import TestResult as QATestResult
        total = QATestResult.objects.filter(project=project).count()
        passed = QATestResult.objects.filter(project=project, status='passed').count()
        failed = QATestResult.objects.filter(project=project, status='failed').count()
        rate = round(passed / max(total, 1) * 100, 1)
        recent = QATestResult.objects.filter(project=project).order_by('-created_at')[:5]
        recent_lines = "\n".join([f"- [{r.status}] {r.name} ({r.test_type})" for r in recent])
        return f"测试统计（项目: {project.name}）：\n- 总执行: {total}, 通过: {passed}, 失败: {failed}\n- 通过率: {rate}%\n- 最近执行:\n{recent_lines or '暂无'}"

    elif tool_name == "get_recent_failures":
        from qa_center.models import TestResult as QATestResult
        limit = int(tool_args.get("limit", 10))
        failures = QATestResult.objects.filter(project=project, status__in=['failed', 'error']).order_by('-created_at')[:limit]
        if not failures.exists():
            return "最近没有失败的测试，太棒了！"
        lines = []
        for f in failures:
            lines.append(f"- [{f.test_type}] {f.name} — {f.error_message or '无错误详情'} ({f.created_at.strftime('%m/%d %H:%M')})")
        return f"最近 {len(lines)} 次失败：\n" + "\n".join(lines)

    return f"未知工具: {tool_name}"
