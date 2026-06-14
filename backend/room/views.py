from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from .models import Project, Column, Task, Tag, Notification
from .serializers import ProjectSerializer, ColumnSerializer, TaskSerializer, UsersSerializer, TagSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from haystack.query import SearchQuerySet
from .ai_utils import get_rag_answer, format_task_context
from backend.throttles import AIRateThrottle

class LoginView(APIView):
    def post(self,request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username = username, password = password)
        if user is not None:
            login(request,user)
            serializer = UsersSerializer(user)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "用户名或密码错误"},
                status=status.HTTP_401_UNAUTHORIZED
            )
class LogoutView(APIView):
    def post(self, request):
        logout(request)
        response = Response({'detail': '注销成功'})
        response.delete_cookie('csrftoken')
        response.delete_cookie('sessionid')
        return response

class CurrentUserView(APIView):
    def get(self, request):
        if request.user.is_authenticated:
            serializer = UsersSerializer(request.user)
            return Response(serializer.data)
        else:
            return Response(
                {"detail": "未登录"},
                status=status.HTTP_401_UNAUTHORIZED
            )
# === 辅助函数：WebSocket 广播 ===
def broadcast_task_change(task_instance, action_type):
    """广播任务变更消息。用于 create/update 操作（任务对象仍然存在）。"""
    try:
        project_id = str(task_instance.column.project.id)
    except AttributeError:
        return
    broadcast_task_change_by_ids(
        str(task_instance.id), task_instance.title, project_id, action_type
    )


def broadcast_task_change_by_ids(task_id, task_title, project_id, action_type):
    """广播任务变更消息。用于所有操作，直接传 ID 而非依赖模型对象。"""
    channel_layer = get_channel_layer()
    room_group_name = f'board_{project_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'board_update',
            "message": {
                "action": 'refresh',
                'task_id': task_id,
                'title': task_title,
                'user_action': action_type
            }
        }
    )

    action_map = {
        "create": "创建了",
        "update": "更新了",
        "delete": "删除了"
    }
    msg_text = action_map.get(action_type, "动了")

    async_to_sync(channel_layer.group_send)(
        "system_broadcast",
        {
            "type": "global_notification",
            "message": f"任务动态：'{task_title}' 被 {msg_text}",
            "level": "success"
        }
    )


# ==========================================
# 1. 看板列 (Column) 的视图
# ==========================================
class ColumnListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # 1. 获取 URL 参数里的 project id
        project_id = request.query_params.get('project')

        if not project_id:
            return Response(
                {"detail": "缺少 project 参数"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. 只查询该项目的列
        columns = Column.objects.filter(project_id=project_id).order_by('position')

        serializer = ColumnSerializer(columns, many=True)
        return Response(serializer.data)

    def post(self, request):
        """新增列"""
        serializer = ColumnSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ColumnDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Column, pk=pk)

    def patch(self, request, pk):
        column = self.get_object(pk)
        serializer = ColumnSerializer(column, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        column = self.get_object(pk)
        if column.tasks.exists():
            return Response({"detail": "该列下还有任务，不能删除"}, status=status.HTTP_400_BAD_REQUEST)
        column.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ==========================================
# 2. 任务 (Task) 的视图 - 列表模式
# ==========================================
class TaskListView(APIView):
    """
    处理 /api/tasks/
    GET: 获取任务列表（支持按项目筛选）
    POST: 创建新任务
    """

    def get(self, request):
        """获取任务列表，支持按项目ID筛选"""
        project_id = request.query_params.get('project')
        if project_id:
            # 获取该项目下所有列的任务
            tasks = Task.objects.filter(column__project_id=project_id)
        else:
            tasks = Task.objects.all()
        serializer = TaskSerializer(tasks, many=True)
        return Response(serializer.data)

    def post(self, request):
        # 1. 拿到前端发来的 JSON 数据 (request.data)
        print("收到创建请求:", request.data)

        # 2. 扔进序列化器进行校验 (检查字段是否完整，格式对不对)
        serializer = TaskSerializer(data=request.data)

        if serializer.is_valid():
            # 3. 校验通过，保存进数据库
            task = serializer.save()

            # 4. 🔥 重点：手动触发广播
            broadcast_task_change(task, "create")

            # 5. 返回创建成功的数据和 201 状态码
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # 6. 校验失败，返回错误信息 (比如标题为空)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================================
# 3. 任务 (Task) 的视图 - 详情模式
# ==========================================
class TaskDetailView(APIView):
    """
    处理 /api/tasks/<task_id>/
    PATCH: 修改任务 (拖拽、改标题、改描述)
    DELETE: 删除任务
    """

    # 辅助方法：根据 ID 找任务，找不到就报 404
    def get_object(self, pk):
        return get_object_or_404(Task, pk=pk)

    def patch(self, request, pk):
        # 1. 找到要修改的任务
        task = self.get_object(pk)

        # 2. partial=True 表示这是部分更新 (比如只改标题，不改 content)
        serializer = TaskSerializer(task, data=request.data, partial=True)

        if serializer.is_valid():
            # 3. 保存修改
            updated_task = serializer.save()

            # 4. 🔥 重点：手动触发广播
            broadcast_task_change(updated_task, "update")

            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        task = self.get_object(pk)

        # 1. 在删除前提取广播所需信息
        task_id = str(task.id)
        task_title = task.title
        try:
            project_id = str(task.column.project.id)
        except AttributeError:
            project_id = None

        # 2. 从数据库删除
        task.delete()

        # 3. 广播
        if project_id:
            broadcast_task_change_by_ids(task_id, task_title, project_id, "delete")

        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskBatchDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        task_ids = request.data.get('task_ids', [])
        if not task_ids:
            return Response({"detail": "未提供任务 ID 列表"}, status=status.HTTP_400_BAD_REQUEST)
        
        tasks = Task.objects.filter(id__in=task_ids)
        project_id = None
        if tasks.exists():
            project_id = str(tasks.first().column.project.id)
            
        # 这里为了简化，我们广播一个全局刷新信号
        count = tasks.count()
        tasks.delete()
        
        if project_id:
            channel_layer = get_channel_layer()
            room_group_name = f'board_{project_id}'
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'board_update',
                    "message": {
                        "action": 'refresh',
                        'user_action': 'batch_delete'
                    }
                }
            )
            
        return Response({"detail": f"成功删除 {count} 个任务"}, status=status.HTTP_200_OK)


class TagListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_id = request.query_params.get('project')
        if not project_id:
            return Response({"detail": "缺少 project 参数"}, status=status.HTTP_400_BAD_REQUEST)
        tags = Tag.objects.filter(project_id=project_id)
        serializer = TagSerializer(tags, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TagSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TagDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Tag, pk=pk)

    def patch(self, request, pk):
        tag = self.get_object(pk)
        serializer = TagSerializer(tag, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        tag = self.get_object(pk)
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserListView(APIView):

    def get(self, request):
        users = User.objects.all()
        serializer = UsersSerializer(users, many=True)
        return Response(serializer.data)


class ProjectListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members=request.user)
        ).distinct().order_by('-created_at')

        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if request.user.is_authenticated:
            data['owner'] = request.user.id

        serializer = ProjectSerializer(data=data)
        if serializer.is_valid():
            # 1. 先保存项目
            project = serializer.save()

            # ✨ 2. 自动创建默认列
            Column.objects.create(project=project, title="To Do", position=1)
            Column.objects.create(project=project, title="In Progress", position=2)
            Column.objects.create(project=project, title="Done", position=3)

            default_tags = [
                {"name": "Bug", "color": "#f56c6c"},  # 红色
                {"name": "Feature", "color": "#409eff"},  # 蓝色
                {"name": "Urgent", "color": "#e6a23c"},  # 橙色
                {"name": "Enhancement", "color": "#67c23a"}  # 绿色
            ]
            for tag in default_tags:
                Tag.objects.create(project=project, name=tag['name'], color=tag['color'])

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            project = Project.objects.get(pk=pk)

            if request.user.is_authenticated and project.owner != request.user:
                 return Response({"detail": "无权删除"}, status=status.HTTP_403_FORBIDDEN)

            project.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

class ProjectInviteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self,request,pk):
        try:
            project = Project.objects.get(pk=pk)

            if request.user.is_authenticated and project.owner != request.user:
                return Response({'detail':'只有项目负责人可以邀请成员'},status=status.HTTP_403_FORBIDDEN)

            username = request.data.get('username')
            user_to_invite = User.objects.get(username=username)
            if user_to_invite == project.owner:
                return Response({"detail": "该用户已经是负责人"}, status=status.HTTP_400_BAD_REQUEST)

            project.members.add(user_to_invite)

            return Response({"detail": f"已邀请 {username} 加入项目"}, status=status.HTTP_200_OK)

        except Project.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        except User.DoesNotExist:
            return Response({"detail": "用户不存在"}, status=status.HTTP_404_NOT_FOUND)


class ProjectChatView(APIView):
    """
    RAG智能项目问答助手
    接收用户问题，搜索相关任务，使用AI生成回答
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AIRateThrottle]

    def post(self, request):
        question = request.data.get('question', '').strip()
        project_id = request.data.get('project_id', '').strip()
        
        if not question:
            return Response(
                {"detail": "问题不能为空"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not project_id:
            return Response(
                {"detail": "项目ID不能为空"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # 1. 验证项目存在且用户有权限访问
            project = get_object_or_404(Project, pk=project_id)
            if request.user != project.owner and request.user not in project.members.all():
                return Response(
                    {"detail": "没有权限访问此项目"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # 2. 使用Haystack搜索相关任务
            # 优先过滤属于当前项目的任务
            search_results = SearchQuerySet().filter(project_id=project_id).auto_query(question).models(Task)
            
            project_tasks = []
            for result in search_results:
                if result.object:
                    project_tasks.append({
                        'id': str(result.object.id),
                        'title': result.object.title,
                        'content': result.object.content or '',
                        'status': result.object.column.title,
                        'assignee': result.object.assignee.username if result.object.assignee else '未指派',
                        'tags': [tag.name for tag in result.object.tags.all()]
                    })
                    if len(project_tasks) >= 5:
                        break
            
            # 3. Fallback 机制：如果搜索结果不足，补充一些最近的任务作为参考
            if len(project_tasks) < 3:
                # 获取该项目下最近更新的 5 个任务（排除已经搜索到的）
                existing_ids = [t['id'] for t in project_tasks]
                fallback_tasks = Task.objects.filter(
                    column__project_id=project_id
                ).exclude(
                    id__in=existing_ids
                ).select_related('column', 'assignee').prefetch_related('tags').order_by('-position')[:5]
                
                for task in fallback_tasks:
                    project_tasks.append({
                        'id': str(task.id),
                        'title': task.title,
                        'content': task.content or '',
                        'status': task.column.title,
                        'assignee': task.assignee.username if task.assignee else '未指派',
                        'tags': [tag.name for tag in task.tags.all()]
                    })
                    if len(project_tasks) >= 8: # 总数不超过8个
                        break
            
            # 4. 构建上下文
            context = format_task_context(project_tasks)
            
            # 4. 调用AI生成回答
            answer = get_rag_answer(question, context)
            
            return Response({
                'answer': answer,
                'context_tasks': project_tasks,  # 返回使用的上下文任务，便于调试
                'question': question
            })
            
        except Exception as e:
            return Response(
                {"detail": f"处理问题时出现错误: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ==================== 通知管理视图 ====================

class NotificationListView(APIView):
    """通知列表视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """获取当前用户的通知列表"""
        project_id = request.query_params.get('project')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        # 基础查询：当前用户的通知
        notifications = Notification.objects.filter(user=request.user)
        
        # 如果指定了项目，筛选该项目相关的通知
        if project_id:
            notifications = notifications.filter(project_id=project_id)
        
        # 计算分页
        total = notifications.count()
        start = (page - 1) * page_size
        end = start + page_size
        notifications = notifications[start:end]
        
        # 序列化
        data = []
        for n in notifications:
            data.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'type': n.type,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
                'project': n.project.id if n.project else None,
            })
        
        return Response({
            'results': data,
            'count': total,
        })


class NotificationReadView(APIView):
    """标记通知已读视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, pk):
        """标记单条通知为已读"""
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({'detail': '已标记为已读'})
        except Notification.DoesNotExist:
            return Response(
                {'detail': '通知不存在'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class NotificationMarkAllReadView(APIView):
    """全部标记已读视图"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """标记所有通知为已读"""
        project_id = request.query_params.get('project')
        
        # 基础查询：当前用户的未读通知
        notifications = Notification.objects.filter(user=request.user, is_read=False)
        
        # 如果指定了项目，筛选该项目相关的通知
        if project_id:
            notifications = notifications.filter(project_id=project_id)
        
        count = notifications.count()
        notifications.update(is_read=True)
        
        return Response({
            'detail': f'已标记 {count} 条通知为已读',
            'count': count,
        })