"""AI 助手视图 — 多轮对话 + 项目分析 + 流式响应 + Tool Calling"""
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.http import StreamingHttpResponse
from django.db.models import Q, Count
from ..models import (
    Project, Task, Column, AIConversation, AIMessage, TaskActivityLog,
)
from ..serializers import AIConversationSerializer, AIMessageSerializer
from ..ai_utils import (
    get_rag_answer, get_streaming_answer, build_project_context,
    AVAILABLE_TOOLS, execute_tool,
)
from backend.throttles import AIRateThrottle
import logging

logger = logging.getLogger(__name__)


def _check_project_member(project, user):
    """检查用户是否为项目成员或所有者"""
    return user == project.owner or project.members.filter(pk=user.pk).exists()


# ============================================================
# 对话列表 / 详情
# ============================================================

class AIConversationListView(APIView):
    """GET /api/ai/conversations/  |  POST"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project_id')
        queryset = AIConversation.objects.filter(user=request.user)
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        serializer = AIConversationSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = AIConversationSerializer(data=data)
        if serializer.is_valid():
            conv = serializer.save()
            return Response(AIConversationSerializer(conv).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AIConversationDetailView(APIView):
    """GET / DELETE /api/ai/conversations/{id}/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, conversation_id):
        conv = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        messages = conv.messages.order_by('created_at')
        return Response({
            'id': conv.id,
            'title': conv.title,
            'project_id': str(conv.project_id) if conv.project_id else None,
            'messages': AIMessageSerializer(messages, many=True).data,
            'created_at': conv.created_at,
            'updated_at': conv.updated_at,
        })

    def delete(self, request, conversation_id):
        conv = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        conv.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# 聊天 (非流式 + Tool Calling)
# ============================================================

class AIChatView(APIView):
    """POST /api/ai/chat/ — 多轮对话 + Tool Calling"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        message = request.data.get('question') or request.data.get('message', '').strip()
        conversation_id = request.data.get('conversation_id')

        if not message:
            return Response({'detail': '问题不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if not project_id:
            return Response({'detail': '项目ID不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        # 获取或创建对话
        if conversation_id:
            conversation = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        else:
            conversation = AIConversation.objects.create(
                user=request.user, project_id=project_id,
                title=message[:50]
            )

        # 保存用户消息
        AIMessage.objects.create(conversation=conversation, role='user', content=message)

        # 构建上下文
        recent_msgs = conversation.messages.order_by('-created_at')[:20]
        history = [{'role': m.role, 'content': m.content} for m in reversed(recent_msgs)]
        context = build_project_context(project_id, message)

        # 尝试 Tool Calling（带工具调用）
        answer, references = self._chat_with_tools(message, context, history, project_id, request.user)

        # 保存 AI 回复
        ai_msg = AIMessage.objects.create(
            conversation=conversation, role='assistant',
            content=answer, references=references
        )
        conversation.updated_at = ai_msg.created_at
        conversation.save(update_fields=['updated_at'])

        return Response({
            'conversation_id': conversation.id,
            'answer': answer,
            'references': references,
            'question': message,
        })

    def _chat_with_tools(self, message: str, context: str, history: list, project_id: str, user):
        """带 Tool Calling 的对话，最多 2 轮工具调用"""
        import openai
        from ..ai_utils import client, SYSTEM_PROMPT_FULL

        messages = [{"role": "system", "content": SYSTEM_PROMPT_FULL}]
        if history:
            for msg in history[-10:]:
                if msg.get('role') in ('user', 'assistant', 'tool'):
                    messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": f"项目上下文：\n{context}\n\n用户：{message}"})

        references = []
        tool_rounds = 0

        while tool_rounds < 3:
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    tools=AVAILABLE_TOOLS,
                    temperature=0.3,
                    max_tokens=2000,
                    timeout=45,
                )
            except Exception as e:
                logger.error(f"AI API error: {e}")
                return f"抱歉，AI 服务暂时不可用: {str(e)}", references

            choice = response.choices[0]
            msg = choice.message

            # No tool calls — return answer
            if not msg.tool_calls:
                return msg.content.strip() if msg.content else "抱歉，无法生成回答。", references

            # Execute tool calls
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result_text = execute_tool(tc.function.name, args, project_id, user)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})
                references.append({"tool": tc.function.name, "args": args, "result": result_text})

            tool_rounds += 1

        # Final summary after tool calls
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", messages=messages,
                temperature=0.3, max_tokens=2000, timeout=45,
            )
            return response.choices[0].message.content.strip(), references
        except Exception as e:
            return f"操作已完成，但生成总结时出错: {str(e)}", references


# ============================================================
# 流式聊天
# ============================================================

class AIStreamChatView(APIView):
    """POST /api/ai/chat/stream/ — 流式响应（不含 Tool Calling，保持低延迟）"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        message = request.data.get('question') or request.data.get('message', '').strip()
        conversation_id = request.data.get('conversation_id')

        if not message or not project_id:
            return Response({'detail': '参数不完整'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        # 获取或创建对话
        if conversation_id:
            conversation = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        else:
            conversation = AIConversation.objects.create(
                user=request.user, project_id=project_id, title=message[:50]
            )

        AIMessage.objects.create(conversation=conversation, role='user', content=message)

        # 历史 + 上下文
        recent_msgs = conversation.messages.order_by('-created_at')[:20]
        history = [{'role': m.role, 'content': m.content} for m in reversed(recent_msgs)]
        context = build_project_context(project_id, message)

        stream = get_streaming_answer(message, context, history=history)

        def generate():
            full_answer = []
            for chunk in stream:
                if chunk:
                    full_answer.append(chunk)
                    yield f'data: {json.dumps({"chunk": chunk}, ensure_ascii=False)}\n\n'
            answer = ''.join(full_answer)
            try:
                AIMessage.objects.create(
                    conversation=conversation, role='assistant',
                    content=answer, references=[]
                )
            except Exception:
                pass
            yield f'data: {json.dumps({"done": True, "conversation_id": conversation.id}, ensure_ascii=False)}\n\n'

        response = StreamingHttpResponse(generate(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


# ============================================================
# 项目分析
# ============================================================

class AIProjectHealthView(APIView):
    """POST /api/ai/analyze/health/ — 项目健康度分析"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        if not project_id:
            return Response({'detail': '项目ID不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        # 使用 build_project_context 收集完整项目数据
        context = build_project_context(project_id, "项目健康度分析")
        answer = get_rag_answer(
            '请分析此项目数据，给出健康度评分(0-100)、Top3风险和改进建议。',
            context,
            system_role='你是项目管理专家。请输出 JSON 格式（如无法输出 JSON 则用结构化文本）: {"score": N, "risks": [...], "suggestions": [...]}'
        )

        # 持久化分析结果
        conv = AIConversation.objects.create(
            user=request.user, project=project,
            title=f'健康度分析 {project.name}'
        )
        AIMessage.objects.create(conversation=conv, role='user', content='项目健康度分析')
        AIMessage.objects.create(conversation=conv, role='assistant', content=answer)

        return Response({
            'project': project.name,
            'analysis': answer,
            'conversation_id': conv.id,
        })


class AIWeeklyReportView(APIView):
    """POST /api/ai/analyze/weekly/ — 周报生成"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        if not project_id:
            return Response({'detail': '项目ID不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        from django.utils import timezone
        from datetime import timedelta
        week_ago = timezone.now() - timedelta(days=7)

        context = build_project_context(project_id, "周报生成")
        answer = get_rag_answer(
            f'请根据以下项目数据（{week_ago.strftime("%m/%d")} ~ {timezone.now().strftime("%m/%d")}）生成一份简洁的周报。',
            context,
            system_role='你是项目周报撰写助手。请用 Markdown 格式输出: ## 本周进展 / ## 下周计划 / ## 风险与问题'
        )

        # 持久化分析结果
        conv = AIConversation.objects.create(
            user=request.user, project=project,
            title=f'周报 {project.name} {timezone.now().strftime("%m/%d")}'
        )
        AIMessage.objects.create(conversation=conv, role='user', content='生成本周项目周报')
        AIMessage.objects.create(conversation=conv, role='assistant', content=answer)

        return Response({
            'project': project.name,
            'weekly_report': answer,
            'conversation_id': conv.id,
        })


class AIRiskIdentificationView(APIView):
    """POST /api/ai/analyze/risks/ — 风险任务识别"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        if not project_id:
            return Response({'detail': '项目ID不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        from django.utils import timezone
        from datetime import timedelta

        # 识别潜在风险任务
        three_days_ago = timezone.now() - timedelta(days=3)
        columns = list(Column.objects.filter(project=project).order_by('position'))
        done_col = None
        for col in columns:
            if any(kw in col.title.lower() for kw in ['done', '完成', '已完成', 'closed']):
                done_col = col
                break
        if not done_col and columns:
            done_col = columns[-1]

        # 风险1: 超过3天未更新的进行中任务
        stale_tasks = Task.objects.filter(
            column__project=project
        ).exclude(column=done_col).filter(
            id__in=TaskActivityLog.objects.filter(
                created_at__lt=three_days_ago,
                task__column__project=project
            ).exclude(task__column=done_col).values('task_id')
        ).select_related('column', 'assignee')[:10]

        # 风险2: 未分配的任务
        unassigned = Task.objects.filter(
            column__project=project, assignee__isnull=True
        ).exclude(column=done_col).select_related('column')[:10]

        # 风险3: 任务最多的成员
        from django.db.models import Count
        overloaded = Task.objects.filter(
            column__project=project, assignee__isnull=False
        ).exclude(column=done_col).values(
            'assignee__username'
        ).annotate(count=Count('id')).order_by('-count')[:5]

        risk_context = "## 潜在风险任务\n\n"
        if stale_tasks.exists():
            risk_context += "### 长期未更新（超过3天）\n"
            for t in stale_tasks:
                risk_context += f"- [{t.column.title}] {t.title} (负责人: {t.assignee.username if t.assignee else '未分配'})\n"

        if unassigned.exists():
            risk_context += f"\n### 未分配任务 ({unassigned.count()} 个)\n"
            for t in unassigned[:5]:
                risk_context += f"- [{t.column.title}] {t.title}\n"

        if overloaded:
            risk_context += "\n### 成员任务分布\n"
            for m in overloaded:
                risk_context += f"- {m['assignee__username']}: {m['count']} 个任务\n"

        if not stale_tasks and not unassigned and not overloaded:
            risk_context += "未发现明显风险，项目运行良好。"

        full_context = build_project_context(project_id, "风险识别") + "\n" + risk_context
        answer = get_rag_answer(
            '请基于以上项目数据，识别该项目中需要关注的风险任务和瓶颈，给出具体建议。',
            full_context,
            system_role='你是项目风险分析师。请识别以下风险类型：长期无进展的任务、未分配的任务、成员任务过载、阻塞问题。输出格式：## 风险概述 / ## 具体风险项 / ## 建议措施。'
        )

        conv = AIConversation.objects.create(
            user=request.user, project=project,
            title=f'风险分析 {project.name}'
        )
        AIMessage.objects.create(conversation=conv, role='user', content='项目风险识别')
        AIMessage.objects.create(conversation=conv, role='assistant', content=answer)

        return Response({
            'project': project.name,
            'analysis': answer,
            'conversation_id': conv.id,
        })


class AISprintSummaryView(APIView):
    """POST /api/ai/analyze/sprint-summary/ — Sprint 总结"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        project_id = request.data.get('project_id', '').strip()
        sprint_id = request.data.get('sprint_id')
        if not project_id:
            return Response({'detail': '项目ID不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        project = get_object_or_404(Project, pk=project_id)
        if not _check_project_member(project, request.user):
            return Response({'detail': '您不是该项目成员'}, status=status.HTTP_403_FORBIDDEN)

        # 如果有指定 sprint，用 sprint 数据；否则汇总所有 sprint
        if sprint_id:
            from ..models import Sprint
            sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
            sprint_tasks = sprint.sprint_tasks.select_related('task__column', 'task__assignee').all()
            sprint_name = sprint.name
            total = sprint_tasks.count()
            columns_info = list(Column.objects.filter(project=project).order_by('position'))
            done_col = None
            for col in columns_info:
                if any(kw in col.title.lower() for kw in ['done', '完成', '已完成', 'closed']):
                    done_col = col
                    break
            completed = sprint_tasks.filter(task__column=done_col).count() if done_col else 0

            sprint_context = f"""## Sprint: {sprint_name}
- 时间: {sprint.start_date} ~ {sprint.end_date}
- 总任务: {total}, 已完成: {completed}, 完成率: {round(completed/total*100,1) if total > 0 else 0}%

### 任务列表
"""
            for st in sprint_tasks[:20]:
                t = st.task
                sprint_context += f"- [{t.column.title}] {t.title} (负责人: {t.assignee.username if t.assignee else '未分配'})\n"
        else:
            sprint_context = "请基于项目整体数据生成 Sprint 总结。"

        full_context = build_project_context(project_id, "Sprint 总结") + "\n" + sprint_context
        answer = get_rag_answer(
            '请基于以上数据生成一份 Sprint 总结报告，包括完成情况、未完成原因分析、下个 Sprint 建议。',
            full_context,
            system_role='你是敏捷教练。请用 Markdown 格式输出: ## Sprint 概览 / ## 完成情况 / ## 未完成分析 / ## 下个 Sprint 建议 / ## 团队表现。'
        )

        conv = AIConversation.objects.create(
            user=request.user, project=project,
            title=f'Sprint 总结 {sprint_name if sprint_id else project.name}'
        )
        AIMessage.objects.create(conversation=conv, role='user', content='生成 Sprint 总结')
        AIMessage.objects.create(conversation=conv, role='assistant', content=answer)

        return Response({
            'project': project.name,
            'analysis': answer,
            'conversation_id': conv.id,
        })
