import sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = r"D:\Projects\SyncBoard\backend\qa_center\views_devops.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = [
    '    def _simulate_test_execution(self, task):\n',
    '        """模拟测试执行（当没有配置测试用例时）"""\n',
    '        logs = []\n',
    '        passed_count = 0\n',
    '        failed_count = 0\n',
    '\n',
    '        # 模拟执行 3-5 个测试用例\n',
    '        test_cases = [1, 2, 3, 4, 5]\n',
    '        for case in test_cases:\n',
    '            time.sleep(0.5)  # 模拟执行时间\n',
    '            success = random.random() > 0.2  # 80%通过率\n',
    '            case_name = f"测试用例 {case}"\n',
    '\n',
    '            logs.append({\n',
    "                'case_id': case,\n",
    "                'case_name': case_name,\n",
    "                'passed': success,\n",
    "                'status_code': 200 if success else 500,\n",
    "                'response_time_ms': random.randint(50, 500),\n",
    "                'message': '模拟通过' if success else '模拟失败',\n",
    "                'request': {\n",
    "                    'method': 'GET',\n",
    "                    'url': f'/api/test/mock-{case}',\n",
    "                    'headers': {},\n",
    "                    'body': None,\n",
    '                },\n',
    "                'response': {\n",
    "                    'status_code': 200 if success else 500,\n",
    "                    'headers': {},\n",
    "                    'body': '{\"mock\": true}',\n",
    '                },\n',
    "                'assertions': [\n",
    '                    {\n',
    "                        'type': 'status_code',\n",
    "                        'field': 'status_code',\n",
    "                        'operator': 'equals',\n",
    "                        'expected_value': 200,\n",
    "                        'actual_value': 200 if success else 500,\n",
    "                        'passed': success,\n",
    "                        'message': '状态码断言通过' if success else '状态码断言失败',\n",
    '                    }\n',
    '                ],\n',
    "                'expected_status': 200,\n",
    "                'expected_response': '{\"mock\": true}',\n",
    "                'timestamp': timezone.now().isoformat(),\n",
    '            })\n',
    '\n',
    '            if success:\n',
    '                passed_count += 1\n',
    '            else:\n',
    '                failed_count += 1\n',
    '\n',
    '        return logs, passed_count, failed_count\n',
]

# Replace lines 585-609 (0-indexed: 584-608)
result = lines[:584] + new_lines + lines[609:]

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(result)

print("OK - _simulate_test_execution replaced")
