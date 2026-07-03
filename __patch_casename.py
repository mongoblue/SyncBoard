import sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = r'D:\Projects\SyncBoard\backend\qa_center\views_devops.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

api_line = '                for result in api_results:\n'
ui_line = '                for result in ui_results:\n'
fallback = "                    if 'case_name' not in result:\n                        result['case_name'] = f\"用例 #{result.get('case_id', '?')}\"\n"

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if line == api_line:
        new_lines.append(fallback)
        print(f'Added case_name fallback after API loop (line {i+1})')
    elif line == ui_line:
        new_lines.append(fallback)
        print(f'Added case_name fallback after UI loop (line {i+1})')

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('OK')
