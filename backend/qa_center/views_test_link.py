"""测试用例↔任务关联视图"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.apps import apps
from room.models import Task, Project
from room.views.mixins import ProjectAccessMixin
from room.serializers import TaskSerializer


# 支持关联的测试用例模型
TEST_CASE_MODELS = {
    'api': 'qa_center.ApiTestCase',
    'ui': 'qa_center.UiTestCase',
    'performance': 'qa_center.PerformanceTestCase',
}


def _get_test_case(test_type, case_id):
    model_path = TEST_CASE_MODELS.get(test_type)
    if not model_path:
        return None
    model = apps.get_model(model_path)
    try:
        return model.objects.get(pk=case_id)
    except model.DoesNotExist:
        return None


class TestCaseLinkTaskView(ProjectAccessMixin, APIView):
    """POST /api/qa/link-task/  — 关联测试用例到任务"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        test_type = request.data.get('test_type')  # 'api'|'ui'|'performance'
        case_id = request.data.get('case_id')
        task_id = request.data.get('task_id')

        if not all([test_type, case_id, task_id]):
            return Response({'detail': '缺少必要参数'}, status=status.HTTP_400_BAD_REQUEST)

        test_case = _get_test_case(test_type, case_id)
        if not test_case:
            return Response({'detail': '测试用例不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 验证项目访问权限
        project, error = self.get_project_with_access(request, str(test_case.project.id))
        if error:
            return error

        try:
            task = Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 验证任务属于同一项目
        if str(task.column.project.id) != str(test_case.project.id):
            return Response({'detail': '任务和测试用例不在同一个项目'}, status=status.HTTP_400_BAD_REQUEST)

        test_case.related_tasks.add(task)
        return Response({'detail': '关联成功'})


class TestCaseUnlinkTaskView(ProjectAccessMixin, APIView):
    """POST /api/qa/unlink-task/  — 取消关联"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        test_type = request.data.get('test_type')
        case_id = request.data.get('case_id')
        task_id = request.data.get('task_id')

        if not all([test_type, case_id, task_id]):
            return Response({'detail': '缺少必要参数'}, status=status.HTTP_400_BAD_REQUEST)

        test_case = _get_test_case(test_type, case_id)
        if not test_case:
            return Response({'detail': '测试用例不存在'}, status=status.HTTP_404_NOT_FOUND)

        project, error = self.get_project_with_access(request, str(test_case.project.id))
        if error:
            return error

        test_case.related_tasks.remove(task_id)
        return Response({'detail': '取消关联成功'})


class TaskLinkedTestsView(ProjectAccessMixin, APIView):
    """GET /api/tasks/{task_id}/linked-tests/  — 查看任务关联的测试用例"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, task_id):
        try:
            task = Task.objects.select_related('column__project').get(pk=task_id)
        except Task.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

        project, error = self.get_project_with_access(request, str(task.column.project.id))
        if error:
            return error

        results = []
        # 收集所有关联的测试用例
        for test_type, model_path in TEST_CASE_MODELS.items():
            model = apps.get_model(model_path)
            cases = model.objects.filter(related_tasks=task)
            for case in cases:
                results.append({
                    'test_type': test_type,
                    'id': case.id,
                    'name': getattr(case, 'name', str(case)),
                    'url': getattr(case, 'url', ''),
                    'method': getattr(case, 'method', ''),
                })

        return Response({'task_id': task_id, 'linked_tests': results, 'count': len(results)})
