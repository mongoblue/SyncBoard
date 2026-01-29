from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from .models import Project, Column, Task,Tag
from .serializers import ProjectSerializer, ColumnSerializer, TaskSerializer, UsersSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q

class LoginView(APIView):
    def post(self,request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username = username, password = password)
        if user is not None:
            login(request,user)
            return Response({
                'id':user.id,
                'username':user.username,
                'email':user.email
            })
        else:
            return Response(
                {"detail": "用户名或密码错误"},
                status=status.HTTP_401_UNAUTHORIZED
            )
class LogoutView(APIView):
    def post(selfself,request):
        logout(request)
        return Response({'detail':'注销成功'})

class CurrentUserView(APIView):
    def get(self, request):
        if request.user.is_authenticated:
            return Response({
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email
            })
        else:
            return Response(
                {"detail": "未登录"},
                status=status.HTTP_401_UNAUTHORIZED
            )
# === 辅助函数：WebSocket 广播 ===
# 把它提出来，作为一个独立的函数，谁需要通知就调用它
def broadcast_task_change(task_instance, action_type):
    """
    手动发送 WebSocket 消息
    :param task_instance: 任务对象 (包含 id, title, column)
    :param action_type: 'create' | 'update' | 'delete'
    """
    channel_layer = get_channel_layer()

    # 1. ✨ 核心修复：动态获取项目 ID
    # 假设你的 Task 关联 Column，Column 关联 Project
    # 如果你的 Task 直接关联 Project，那就用 task_instance.project.id
    try:
        project_id = str(task_instance.column.project.id)
        room_group_name = f'board_{project_id}'
    except AttributeError:
        # 如果是删除操作传进来的 TempTask 对象，可能没有 column 关联了
        # 这里需要特别处理，或者在删除前就把 project_id 传进来
        # 简单起见，我们假设 task_instance 里依然能访问到 project_id
        # 如果 delete 时传的是临时对象，请确保它有 project_id 属性
        print("⚠️ 无法获取项目ID，广播失败")
        return

    # 2. 发送给该项目的房间
    async_to_sync(channel_layer.group_send)(
        room_group_name,  # 👈 修正：发给 board_{uuid}
        {
            'type': 'board_update', # 👈 确保和 consumers.py 里的方法名一致
            "message": {
                "action": 'refresh',
                'task_id': str(task_instance.id),
                'title': task_instance.title,
                'user_action': action_type
            }
        }
    )

    # 2. 发送全局弹窗通知 (给 GlobalConsumer 发消息)
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
            "message": f"任务动态：'{task_instance.title}' 被 {msg_text}",
            "level": "success"
        }
    )
    print(f"📢 广播成功: {action_type} - {task_instance.title}")


# ==========================================
# 1. 看板列 (Column) 的视图
# ==========================================
class ColumnListView(APIView):

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


# ==========================================
# 2. 任务 (Task) 的视图 - 列表模式
# ==========================================
class TaskListView(APIView):
    """
    处理 /api/tasks/
    POST: 创建新任务
    """

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

        # 1. 记录必要信息 (用于广播)
        class TempTask:
            id = str(task.id)
            title = task.title
            # ✨ 核心：手动构造一个结构，骗过 broadcast 函数
            class Column:
                class Project:
                    id = str(task.column.project.id)
                project = Project()
            column = Column()

        temp_info = TempTask()

        # 2. 从数据库删除
        task.delete()

        # 3. 广播
        broadcast_task_change(temp_info, "delete")

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