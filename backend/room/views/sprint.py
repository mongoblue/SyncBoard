"""迭代/Sprint 视图"""
from datetime import date, timedelta
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Min
from ..models import Sprint, SprintTask, Task, Column, TaskActivityLog, Project
from ..serializers import SprintSerializer, SprintTaskSerializer
from .mixins import ProjectAccessMixin


def _find_done_column(project, columns=None):
    """智能查找项目的'已完成'列"""
    if columns is None:
        columns = list(Column.objects.filter(project=project).order_by('position'))
    if not columns:
        return None
    done_keywords = ['done', '完成', '已完成', 'closed', '已关闭', 'complete', 'finished']
    for col in columns:
        if any(kw in col.title.lower() for kw in done_keywords):
            return col
    return columns[-1]


class SprintListView(ProjectAccessMixin, APIView):
    """GET /api/projects/{pid}/sprints/  |  POST"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprints = Sprint.objects.filter(project=project)
        serializer = SprintSerializer(sprints, many=True)
        return Response(serializer.data)

    def post(self, request, project_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        data = request.data.copy()
        data['project'] = project_id
        serializer = SprintSerializer(data=data)
        if serializer.is_valid():
            sprint = serializer.save()
            return Response(SprintSerializer(sprint).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SprintDetailView(ProjectAccessMixin, APIView):
    """GET/PUT/DELETE /api/projects/{pid}/sprints/{sid}/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id, sprint_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
        serializer = SprintSerializer(sprint)
        return Response(serializer.data)

    def put(self, request, project_id, sprint_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
        serializer = SprintSerializer(sprint, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, project_id, sprint_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
        sprint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SprintTaskView(ProjectAccessMixin, APIView):
    """POST/DELETE /api/projects/{pid}/sprints/{sid}/tasks/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, project_id, sprint_id):
        """添加任务到迭代"""
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
        task_id = request.data.get('task_id')
        if not task_id:
            return Response({'detail': '缺少 task_id'}, status=status.HTTP_400_BAD_REQUEST)

        task = get_object_or_404(Task, pk=task_id)
        # 验证任务属于同一项目
        if str(task.column.project.id) != str(project_id):
            return Response({'detail': '任务不属于此项目'}, status=status.HTTP_400_BAD_REQUEST)

        st, created = SprintTask.objects.get_or_create(sprint=sprint, task=task)
        if not created:
            return Response({'detail': '任务已在迭代中'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SprintTaskSerializer(st)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, project_id, sprint_id):
        """从迭代移除任务"""
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({'detail': '缺少 task_id'}, status=status.HTTP_400_BAD_REQUEST)

        st = get_object_or_404(SprintTask, sprint=sprint, task_id=task_id)
        st.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SprintBurndownView(ProjectAccessMixin, APIView):
    """GET /api/projects/{pid}/sprints/{sid}/burndown/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id, sprint_id):
        project, error = self.get_project_with_access(request, project_id)
        if error:
            return error
        sprint = get_object_or_404(Sprint, pk=sprint_id, project=project)

        total_tasks = sprint.sprint_tasks.count()
        if total_tasks == 0:
            return Response({
                'sprint_id': sprint_id, 'sprint_name': sprint.name,
                'total_tasks': 0, 'burndown': [],
            })

        columns = list(Column.objects.filter(project=project).order_by('position'))
        done_col = _find_done_column(project, columns)

        start = sprint.start_date
        end = min(sprint.end_date, date.today())
        delta = (end - start).days
        if delta <= 0:
            return Response({'ideal': [], 'actual': [], 'total': total_tasks})

        # Build per-day completion count from TaskActivityLog
        sprint_task_ids = list(sprint.sprint_tasks.values_list('task_id', flat=True))
        completion_dates = defaultdict(int)

        if done_col and sprint_task_ids:
            # Find when each sprint task was moved TO the done column
            done_moves = TaskActivityLog.objects.filter(
                task_id__in=sprint_task_ids,
                field_name='column',
                action='moved',
            ).values('task_id', 'created_at__date').order_by('created_at')

            # Track the earliest move-to-done date per task
            seen_tasks = set()
            for move in done_moves:
                if move['task_id'] not in seen_tasks:
                    seen_tasks.add(move['task_id'])
                    d = move['created_at__date']
                    if d:
                        completion_dates[d] += 1

        # Tasks already in Done column at sprint start (completed before or at start)
        if done_col:
            already_done = sprint.sprint_tasks.filter(
                task__column=done_col
            ).exclude(task_id__in=seen_tasks).count()
        else:
            already_done = 0

        burndown = []
        cumulative_completed = already_done

        for i in range(delta + 1):
            day = start + timedelta(days=i)
            cumulative_completed += completion_dates.get(day, 0)
            remaining = total_tasks - cumulative_completed
            ideal_remaining = total_tasks - (total_tasks * i / delta)

            burndown.append({
                'date': day.isoformat(),
                'remaining': remaining,
                'ideal': round(ideal_remaining, 1),
            })

        return Response({
            'sprint_id': sprint_id,
            'sprint_name': sprint.name,
            'total_tasks': total_tasks,
            'burndown': burndown,
        })
