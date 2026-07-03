import sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = r'D:\Projects\SyncBoard\frontend\src\views\qa\TestResultDetail.vue'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Patch 1: Replace caseResults computed (lines 483-499, 0-indexed: 482-498)
old_case_results = [
    'const caseResults = computed(() => {\n',
    '  if (!result.value?.test_log) return [];\n',
    '  try {\n',
    '    const log = JSON.parse(result.value.test_log);\n',
    '    // 新格式: { summary: {}, results: [] }\n',
    '    if (log.results && Array.isArray(log.results)) {\n',
    '      return log.results;\n',
    '    }\n',
    '    // 旧格式兼容: 直接是数组\n',
    '    if (Array.isArray(log)) {\n',
    '      return log;\n',
    '    }\n',
    '    return [];\n',
    '  } catch {\n',
    '    return [];\n',
    '  }\n',
    '});\n',
]

new_case_results = [
    'const caseResults = computed(() => {\n',
    '  if (!result.value?.test_log) return [];\n',
    '  try {\n',
    '    const log = JSON.parse(result.value.test_log);\n',
    '    let items = [];\n',
    '    // 新格式: { summary: {}, results: [] }\n',
    '    if (log.results && Array.isArray(log.results)) {\n',
    '      items = log.results;\n',
    '    }\n',
    '    // 旧格式兼容: 直接是数组\n',
    '    else if (Array.isArray(log)) {\n',
    '      items = log;\n',
    '    }\n',
    '    // 兼容模拟执行结果：将 status 字段转换为 passed 布尔值\n',
    '    return items.map((item: any) => ({\n',
    '      ...item,\n',
    '      passed: item.passed !== undefined\n',
    '        ? item.passed\n',
    '        : (item.status === \x27passed\x27),\n',
    '      case_name: item.case_name || item.case || 用例 #,\n',
    '    }));\n',
    '  } catch {\n',
    '    return [];\n',
    '  }\n',
    '});\n',
]

# Verify the old lines match
for i in range(16):
    if lines[482 + i].rstrip() != old_case_results[i].rstrip():
        print(f'MISMATCH at line {483+i}:')
        print(f'  expected: {old_case_results[i].rstrip()}')
        print(f'  actual:   {lines[482+i].rstrip()}')
        sys.exit(1)

# Replace
lines[482:498] = new_case_results
print('caseResults computed replaced')

# Patch 2: Add empty data hint after line 249 (0-indexed: 248)
empty_hint = '              <!-- 无详细数据时的提示 -->\n              <div v-if=\"!caseResult.request && !caseResult.response && !caseResult.assertions?.length\" class=\"detail-section\">\n                <el-empty description=\"此用例无详细执行数据（可能为模拟执行或执行异常）\" :image-size=\"80\" />\n              </div>\n'
lines.insert(249, empty_hint)
print('Empty data hint added')

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('OK')
