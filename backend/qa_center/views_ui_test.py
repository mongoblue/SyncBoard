"""
UI 测试用例视图
E2E 自动化测试相关接口
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
import requests

from .models import UiTestCase
from .serializers import UiTestCaseSerializer, UiTestCaseListSerializer, UiTestCaseRunSerializer
from .utils.runner import run_ui_case


class UiTestCaseViewSet(viewsets.ModelViewSet):
    """UI 测试用例 ViewSet"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = UiTestCaseSerializer
    
    def get_queryset(self):
        """根据项目过滤"""
        queryset = UiTestCase.objects.all()
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset.select_related('created_by')
    
    def get_serializer_class(self):
        """根据动作选择序列化器"""
        if self.action == 'list':
            return UiTestCaseListSerializer
        return UiTestCaseSerializer
    
    def perform_create(self, serializer):
        """创建时设置创建者"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """
        运行 UI 测试用例
        
        POST /api/qa/ui-cases/{id}/run/
        
        Returns:
            {
                "success": true,
                "screenshot": "data:image/png;base64,...",
                "logs": ["..."],
                "error": null
            }
        """
        # 获取测试用例
        test_case = self.get_object()
        
        # 准备测试数据
        case_data = {
            'url': test_case.url,
            'steps': test_case.steps or []
        }
        
        # 运行测试
        result = run_ui_case(case_data)

        # 【修复】先返回 HTTP 响应，再在后台保存测试结果
        import threading
        import traceback
        
        def save_result_in_background():
            """在后台线程中保存测试结果"""
            try:
                print(f"[DEBUG] 开始在后台保存测试结果，test_case={test_case.name}, success={result.get('success')}")
                self._save_test_result(test_case, result, request)
                print("[DEBUG] 后台保存测试结果完成")
            except Exception as e:
                print(f"[ERROR] 后台保存测试结果失败: {e}")
                print(f"[ERROR] 详细错误: {traceback.format_exc()}")
        
        # 启动后台线程保存结果
        thread = threading.Thread(target=save_result_in_background)
        thread.daemon = True
        thread.start()
        print(f"[DEBUG] 已启动后台线程保存测试结果")

        # 直接返回结果，不经过序列化器验证（避免截图数据过大导致验证问题）
        return Response(result, status=status.HTTP_200_OK)
    
    def _save_test_result(self, test_case, result, request):
        """保存测试结果"""
        from django.conf import settings
        from django.utils import timezone
        from datetime import datetime
        import base64
        import os
        import uuid
        import logging

        logger = logging.getLogger('django')

        try:
            # 导入模型
            from .models import TestResult, TestScreenshot

            logger.info(f"开始保存UI测试结果: {test_case.name}")

            # 创建测试结果记录
            test_result = TestResult.objects.create(
                test_type='ui',
                name=test_case.name,
                project=test_case.project,
                ui_test_case=test_case,
                executed_by=request.user,
                status='passed' if result.get('success') else 'failed',
                test_steps=test_case.steps or [],
                actual_result='测试完成' if result.get('success') else result.get('error', ''),
                error_message=result.get('error', ''),
                test_log='\n'.join(result.get('logs', [])),
                started_at=timezone.now(),
                completed_at=timezone.now()
            )

            logger.info(f"测试结果记录已创建: ID={test_result.id}")

            # 保存步骤截图
            step_screenshots = result.get('step_screenshots', [])
            if step_screenshots:
                logger.info(f"开始保存 {len(step_screenshots)} 个步骤截图")
                for step_data in step_screenshots:
                    step_num = step_data.get('step', 0)
                    screenshot_base64 = step_data.get('screenshot')
                    
                    if screenshot_base64:
                        try:
                            # 从 base64 字符串创建图片
                            if ',' in screenshot_base64:
                                screenshot_base64 = screenshot_base64.split(',')[1]

                            image_data = base64.b64decode(screenshot_base64)

                            # 生成文件名
                            filename = f"ui_test_step{step_num}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"

                            # 保存到媒体目录
                            screenshot_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                            full_dir = os.path.join(settings.MEDIA_ROOT, screenshot_dir)
                            os.makedirs(full_dir, exist_ok=True)

                            filepath = os.path.join(full_dir, filename)
                            with open(filepath, 'wb') as f:
                                f.write(image_data)

                            # 创建截图记录
                            screenshot = TestScreenshot.objects.create(
                                test_result=test_result,
                                name=f'步骤 {step_num} 截图',
                                description=f'步骤 {step_num} 执行后的页面截图',
                                image=os.path.join(screenshot_dir, filename)
                            )

                            logger.info(f"步骤 {step_num} 截图已保存: ID={screenshot.id}")

                        except Exception as e:
                            logger.error(f"保存步骤 {step_num} 截图失败: {e}")
            
            # 保存最终截图（如果有且不在步骤截图中）
            final_screenshot = result.get('screenshot')
            if final_screenshot:
                # 检查是否已经在步骤截图中保存过了
                already_saved = False
                for step_data in step_screenshots:
                    if step_data.get('screenshot') == final_screenshot:
                        already_saved = True
                        break
                
                if not already_saved:
                    try:
                        # 从 base64 字符串创建图片
                        if ',' in final_screenshot:
                            final_screenshot = final_screenshot.split(',')[1]

                        image_data = base64.b64decode(final_screenshot)

                        # 生成文件名
                        filename = f"ui_test_final_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"

                        # 保存到媒体目录
                        screenshot_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                        full_dir = os.path.join(settings.MEDIA_ROOT, screenshot_dir)
                        os.makedirs(full_dir, exist_ok=True)

                        filepath = os.path.join(full_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(image_data)

                        # 创建截图记录
                        screenshot = TestScreenshot.objects.create(
                            test_result=test_result,
                            name='最终截图',
                            description='测试完成后的最终页面截图',
                            image=os.path.join(screenshot_dir, filename)
                        )

                        logger.info(f"最终截图已保存: ID={screenshot.id}")

                    except Exception as e:
                        logger.error(f"保存最终截图失败: {e}")
            
            if not step_screenshots and not final_screenshot:
                logger.warning("没有截图数据需要保存")

        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    @action(detail=True, methods=['get'], url_path='linked-tasks')
    def linked_tasks(self, request, pk=None):
        test_case = self.get_object()
        tasks = test_case.related_tasks.select_related('column', 'assignee').prefetch_related('tags')
        from room.serializers import TaskSerializer
        return Response(TaskSerializer(tasks, many=True).data)

    @action(detail=False, methods=['post'])
    def run_temp(self, request):
        """
        临时运行 UI 测试（不保存用例）
        
        POST /api/qa/ui-cases/run_temp/
        
        Request Body:
            {
                "url": "https://example.com",
                "steps": [
                    {"action": "click", "selector": "#btn", "value": ""},
                    {"action": "fill", "selector": "#input", "value": "text"}
                ]
            }
        
        Returns:
            同 run 接口
        """
        url = request.data.get('url', '')
        steps = request.data.get('steps', [])
        
        if not url:
            return Response(
                {'error': '请提供起始 URL'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 准备测试数据
        case_data = {
            'url': url,
            'steps': steps
        }
        
        # 运行测试
        result = run_ui_case(case_data)

        # 直接返回结果，不经过序列化器验证（避免截图数据过大导致验证问题）
        return Response(result, status=status.HTTP_200_OK)


def execute_ui_test_cases(case_ids):
    """
    批量执行 UI 测试用例
    :param case_ids: 测试用例ID列表
    :return: 执行结果列表
    """
    from .utils.runner import run_ui_case
    from django.utils import timezone
    import base64
    import os
    import uuid
    from datetime import datetime
    from django.conf import settings
    
    results = []
    
    for case_id in case_ids:
        try:
            test_case = UiTestCase.objects.get(id=case_id)
            
            # 准备测试数据
            case_data = {
                'url': test_case.url,
                'steps': test_case.steps or []
            }
            
            # 运行测试
            result = run_ui_case(case_data)
            
            # 保存测试结果
            screenshot_url = None
            try:
                from .models import TestResult, TestScreenshot
                
                test_result = TestResult.objects.create(
                    test_type='ui',
                    name=test_case.name,
                    project=test_case.project,
                    ui_test_case=test_case,
                    executed_by=None,  # 系统执行
                    status='passed' if result.get('success') else 'failed',
                    test_steps=test_case.steps or [],
                    actual_result='测试完成' if result.get('success') else result.get('error', ''),
                    error_message=result.get('error', ''),
                    test_log='\n'.join(result.get('logs', [])),
                    started_at=timezone.now(),
                    completed_at=timezone.now()
                )
                
                # 保存截图
                screenshot_base64 = result.get('screenshot')
                if screenshot_base64:
                    try:
                        if ',' in screenshot_base64:
                            screenshot_base64 = screenshot_base64.split(',')[1]
                        
                        image_data = base64.b64decode(screenshot_base64)
                        filename = f"ui_test_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}.png"
                        screenshot_dir = os.path.join('test_screenshots', datetime.now().strftime('%Y/%m/%d'))
                        full_dir = os.path.join(settings.MEDIA_ROOT, screenshot_dir)
                        os.makedirs(full_dir, exist_ok=True)
                        
                        filepath = os.path.join(full_dir, filename)
                        with open(filepath, 'wb') as f:
                            f.write(image_data)
                        
                        screenshot = TestScreenshot.objects.create(
                            test_result=test_result,
                            name='UI测试截图',
                            description='自动化测试执行截图',
                            image=os.path.join(screenshot_dir, filename)
                        )
                        screenshot_url = screenshot.image.url if hasattr(screenshot.image, 'url') else str(screenshot.image)
                    except Exception as e:
                        print(f"保存截图失败: {e}")
                
                # 构建步骤执行结果
                steps_result = []
                for i, step in enumerate(test_case.steps or []):
                    step_logs = [log for log in result.get('logs', []) if f'步骤 {i+1}' in log or step.get('action', '') in log]
                    steps_result.append({
                        'step_number': i + 1,
                        'action': step.get('action', ''),
                        'selector': step.get('selector', ''),
                        'value': step.get('value', ''),
                        'status': 'passed' if result.get('success') else 'failed',
                        'logs': step_logs
                    })
                
                results.append({
                    'case_id': case_id,
                    'case_name': test_case.name,
                    'passed': result.get('success', False),
                    'type': 'ui',
                    'message': '测试完成' if result.get('success') else result.get('error', '测试失败'),
                    'request': {
                        'method': 'UI',
                        'url': test_case.url,
                        'headers': {},
                        'body': {'steps': test_case.steps or []}
                    },
                    'response': {
                        'status_code': 200 if result.get('success') else 500,
                        'body': result.get('error', '') if not result.get('success') else '测试完成',
                        'headers': {}
                    },
                    'steps': steps_result,
                    'screenshot_url': screenshot_url,
                    'assertions': []
                })
                
            except Exception as e:
                results.append({
                    'case_id': case_id,
                    'case_name': test_case.name,
                    'passed': False,
                    'screenshot': None,
                    'message': f'保存结果失败: {str(e)}'
                })
                
        except UiTestCase.DoesNotExist:
            results.append({
                'case_id': case_id,
                'case_name': '未知用例',
                'passed': False,
                'screenshot': None,
                'message': '测试用例不存在'
            })
    
    return results
