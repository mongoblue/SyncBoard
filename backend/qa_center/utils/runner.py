"""
Playwright UI 测试运行器
用于执行 E2E 自动化测试
"""

import base64
import json
import logging
import os
import tempfile
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from django.conf import settings

logger = logging.getLogger('django')


class PlaywrightRunner:
    """Playwright UI 测试运行器"""

    def __init__(self):
        self.logs: List[str] = []
        self.temp_dir = None
        self.step_screenshot = None

    def log(self, message: str):
        """记录日志"""
        self.logs.append(message)
        logger.info(message)

    def _setup_temp_dir(self):
        """设置临时目录，避免 Windows 权限问题"""
        base_temp = os.path.join(settings.BASE_DIR, '.playwright-temp')
        os.makedirs(base_temp, exist_ok=True)
        self.temp_dir = tempfile.mkdtemp(prefix='run_', dir=base_temp)
        os.environ['PLAYWRIGHT_TEMP_DIR'] = self.temp_dir
        os.environ['TEMP'] = self.temp_dir
        os.environ['TMP'] = self.temp_dir
        return self.temp_dir

    def _cleanup_temp_dir(self):
        """清理临时目录"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

    def _find_exact_text_match(self, page, text: str, tag: str = '*', context_selector: str = None):
        """
        查找文本完全匹配的元素
        遍历所有匹配的元素，返回文本完全匹配的那个
        
        Args:
            page: Playwright page 对象
            text: 要查找的文本
            tag: 标签名（已弃用，保留兼容性）
            context_selector: 上下文选择器，如果提供，会优先在指定区域内查找
        """
        if context_selector:
            try:
                context_locator = self._get_locator(page, context_selector)
                locator_in_context = context_locator.get_by_text(text, exact=False)
                count_in_context = locator_in_context.count()
                if count_in_context > 0:
                    self.log(f"   在指定上下文中找到 {count_in_context} 个匹配 '{text}' 的元素")
                    return locator_in_context.first
            except Exception as e:
                self.log(f"   ⚠️ 在上下文中查找失败: {e}，尝试全局查找")
        
        locator = page.get_by_text(text, exact=False)
        count = locator.count()
        if count == 0:
            raise Exception(f"找不到包含文本 '{text}' 的元素")
        
        if count == 1:
            return locator.first
        
        self.log(f"   找到 {count} 个匹配 '{text}' 的元素，使用智能匹配...")
        
        # 策略1：优先选择可见的下拉选项元素
        for i in range(count):
            try:
                element = locator.nth(i)
                is_option_item = element.locator('xpath=self[contains(@class, "el-select-dropdown__item") or contains(@class, "el-dropdown-menu__item") or ancestor::*[contains(@class, "el-select-dropdown__item") or contains(@class, "el-dropdown-menu__item")]]').count() > 0
                if is_option_item:
                    if element.is_visible():
                        self.log(f"   ✅ 找到可见的下拉选项元素 (第 {i+1} 个)")
                        return element
            except Exception as e:
                continue
        
        # 策略2：选择在下拉框内且可见的元素
        for i in range(count):
            try:
                element = locator.nth(i)
                is_in_dropdown = element.locator('xpath=ancestor::*[contains(@class, "el-select-dropdown") or contains(@class, "el-dropdown-menu")]').count() > 0
                if is_in_dropdown and element.is_visible():
                    self.log(f"   ✅ 找到在下拉框内可见的元素 (第 {i+1} 个)")
                    return element
            except Exception as e:
                continue
        
        # 策略3：选择文本完全匹配的元素
        for i in range(count):
            try:
                element = locator.nth(i)
                element_text = element.text_content(timeout=5000)
                if element_text and element_text.strip() == text.strip():
                    self.log(f"   ✅ 找到文本完全匹配的元素 (第 {i+1} 个)")
                    return element
            except Exception as e:
                continue
        
        # 策略4：选择文本包含目标文本的元素
        for i in range(count):
            try:
                element = locator.nth(i)
                element_text = element.text_content(timeout=5000)
                if element_text and text in element_text:
                    self.log(f"   ✅ 找到包含目标文本的元素 (第 {i+1} 个)")
                    return element
            except Exception as e:
                continue
        
        self.log(f"   ⚠️ 未找到精确匹配，使用第一个匹配的元素")
        return locator.first

    def _get_locator(self, page, selector: Any):
        """
        根据选择器获取 Playwright Locator
        支持多种选择器类型：role, text, testId, css
        """
        if isinstance(selector, str):
            if ' >> nth=' in selector:
                parts = selector.split(' >> nth=')
                base_selector = parts[0]
                nth_index = int(parts[1])
                base_locator = self._get_locator(page, base_selector)
                return base_locator.nth(nth_index)
            
            if selector.startswith('role='):
                parts = selector[5:].split(',', 1)
                role = parts[0].strip()
                name = parts[1].strip().strip('"\'') if len(parts) > 1 else None
                if name:
                    return page.get_by_role(role, name=name)
                return page.get_by_role(role)
            
            if selector.startswith('text='):
                return page.get_by_text(selector[5:], exact=False)
            
            if selector.startswith('text-exact='):
                return page.get_by_text(selector[11:], exact=True)
            
            if selector.startswith('testId=') or selector.startswith('data-testid='):
                test_id = selector.split('=', 1)[1]
                return page.get_by_test_id(test_id)
            
            if selector.startswith('placeholder='):
                placeholder = selector.split('=', 1)[1]
                return page.get_by_placeholder(placeholder)
            
            if selector.startswith('label='):
                label = selector.split('=', 1)[1]
                return page.get_by_label(label)
            
            if ':has-text(' in selector:
                import re
                text_match = re.search(r':has-text\("([^"]+)"\)', selector)
                if text_match:
                    text = text_match.group(1)
                    base_selector = re.sub(r':has-text\("[^"]+"\)', '', selector)
                    if base_selector.strip():
                        return page.locator(base_selector).get_by_text(text, exact=False)
                    return self._find_exact_text_match(page, text)
            
            return page.locator(selector).first
        
        return selector

    def _is_dropdown_option(self, locator) -> bool:
        """
        检测元素是否是下拉框选项（真正的选项，不是触发器）
        """
        try:
            # 检查元素是否在下拉面板内（包括 el-popper）
            is_in_dropdown_panel = locator.locator(
                'xpath=ancestor::*[contains(@class, "el-select-dropdown") or contains(@class, "el-dropdown-menu") or contains(@class, "el-popper") or contains(@class, "el-select__popper")]'
            ).count() > 0

            if not is_in_dropdown_panel:
                return False

            # 检查元素是否是选项项
            try:
                classes = locator.evaluate('el => el.className || ""')
                if isinstance(classes, str):
                    option_classes = ['el-select-dropdown__item', 'el-dropdown-menu__item', 'el-option']
                    for cls in option_classes:
                        if cls in classes:
                            return True
            except:
                pass

            # 检查元素或其父元素是否是选项项
            is_option_item = locator.locator(
                'xpath=self[contains(@class, "el-select-dropdown__item") or contains(@class, "el-dropdown-menu__item") or ancestor::*[contains(@class, "el-select-dropdown__item") or contains(@class, "el-dropdown-menu__item")]]'
            ).count() > 0

            return is_option_item

        except Exception as e:
            return False

    def _is_in_el_select(self, locator) -> bool:
        """
        检测元素是否在 el-select 组件内（触发器区域，不包括下拉面板）
        """
        try:
            # 检查是否在下拉面板内（包括 el-popper），如果是则返回 False
            is_in_dropdown_panel = locator.locator(
                'xpath=ancestor::*[contains(@class, "el-select-dropdown") or contains(@class, "el-dropdown-menu") or contains(@class, "el-popper") or contains(@class, "el-select__popper")]'
            ).count() > 0
            if is_in_dropdown_panel:
                return False

            # 检查是否在 el-select 组件内
            return locator.locator('xpath=ancestor::*[contains(@class, "el-select")]').count() > 0
        except Exception as e:
            return False

    def _click_el_select_trigger(self, page, locator):
        """
        点击 el-select 的触发器打开下拉框
        """
        try:
            select_element = locator.locator('xpath=ancestor::*[contains(@class, "el-select")]').first
            if select_element.count() == 0:
                self.log("   ⚠️ 未找到 el-select 父元素")
                locator.click(timeout=5000)
                return

            self.log("   检测到 el-select 组件，点击触发器...")

            trigger = select_element.locator('.el-select__wrapper, .el-input, .el-select__input').first
            if trigger.count() > 0:
                self.log("   点击 el-select 触发区域...")
                trigger.click(timeout=5000)
            else:
                self.log("   点击 el-select 整体...")
                select_element.click(timeout=5000)

            page.wait_for_timeout(300)

            try:
                dropdown = page.locator('.el-select-dropdown:visible').first
                dropdown.wait_for(state='visible', timeout=2000)
                self.log("   ✅ 下拉框已打开")
            except:
                self.log("   ⚠️ 下拉框可能未打开")

        except Exception as e:
            self.log(f"   ⚠️ el-select 点击失败: {e}")
            try:
                locator.click(timeout=5000)
            except:
                pass

    def _click_dropdown_option_v2(self, page, locator):
        """
        点击下拉框选项（改进版）
        """
        option_text = ""
        try:
            option_text = locator.text_content(timeout=2000) or ""
            self.log(f"   选项文本: {option_text.strip()}")
        except:
            pass

        try:
            visible_panels = page.locator('.el-select-dropdown:visible, .el-popper:visible').all()
            self.log(f"   当前可见的下拉面板数量: {len(visible_panels)}")
        except:
            pass

        try:
            all_options = page.locator('.el-select-dropdown__item, .el-dropdown-menu__item').all()
            self.log(f"   页面上所有下拉选项数量: {len(all_options)}")
            for i, opt in enumerate(all_options[:5]):
                try:
                    opt_text = opt.text_content(timeout=1000) or ""
                    opt_visible = opt.is_visible()
                    self.log(f"   选项[{i}]: '{opt_text.strip()[:30]}' 可见={opt_visible}")
                except:
                    pass
        except:
            pass

        self.log("   策略1: 在可见下拉面板内查找...")
        try:
            visible_dropdown = page.locator('.el-select-dropdown:visible').first
            if visible_dropdown.count() > 0:
                option_in_panel = visible_dropdown.locator('.el-select-dropdown__item, .el-dropdown-menu__item').filter(
                    has_text=option_text.strip() if option_text else ""
                ).first
                if option_in_panel.count() > 0:
                    self.log(f"   在可见下拉面板内找到选项")
                    option_in_panel.evaluate('el => el.click()')
                    self.log("   ✅ JavaScript click 成功")
                    page.wait_for_timeout(300)
                    return
        except Exception as e:
            self.log(f"   ⚠️ 策略1失败: {str(e)[:80]}...")

        self.log("   策略2: 查找可见的下拉选项...")
        try:
            visible_options = page.locator('.el-select-dropdown__item:visible, .el-dropdown-menu__item:visible').all()
            self.log(f"   可见选项数量: {len(visible_options)}")
            for opt in visible_options:
                try:
                    opt_text = opt.text_content(timeout=1000) or ""
                    if option_text.strip() in opt_text:
                        self.log(f"   找到匹配的可见选项: '{opt_text.strip()[:30]}'")
                        opt.evaluate('el => el.click()')
                        self.log("   ✅ JavaScript click 成功")
                        page.wait_for_timeout(300)
                        return
                except:
                    continue
        except Exception as e:
            self.log(f"   ⚠️ 策略2失败: {str(e)[:80]}...")

        self.log("   策略3: 使用原始 locator...")
        try:
            if locator.is_visible():
                self.log("   原始 locator 可见，尝试 JavaScript click")
                locator.evaluate('el => el.click()')
                self.log("   ✅ JavaScript click 成功")
                page.wait_for_timeout(300)
                return
        except Exception as e:
            self.log(f"   ⚠️ 策略3失败: {str(e)[:80]}...")

        self.log("   策略4: 强制点击...")
        try:
            locator.click(force=True, timeout=5000)
            self.log("   ✅ 强制点击成功")
            page.wait_for_timeout(300)
            return
        except Exception as e:
            self.log(f"   ⚠️ 策略4失败: {str(e)[:80]}...")

        self.log("   策略5: 通过文本直接查找...")
        try:
            text_locator = page.get_by_text(option_text, exact=False).first
            text_locator.evaluate('el => el.click()')
            self.log("   ✅ 文本查找点击成功")
            page.wait_for_timeout(300)
            return
        except Exception as e:
            self.log(f"   ❌ 所有策略都失败: {str(e)[:80]}...")
            raise Exception(f"无法点击下拉选项: {option_text}")

    def _hover_dropdown_option(self, page, locator):
        """
        悬停下拉框选项
        """
        option_text = ""
        try:
            option_text = locator.text_content(timeout=2000) or ""
            self.log(f"   选项文本: {option_text.strip()}")
        except:
            pass

        self.log("   悬停选项...")
        try:
            locator.hover(timeout=5000)
            self.log("   ✅ 悬停成功")
        except Exception as e:
            self.log(f"   ⚠️ 普通悬停失败: {str(e)[:100]}...")
            try:
                locator.evaluate('el => el.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }))')
                self.log("   ✅ JavaScript mouseenter 成功")
            except Exception as e2:
                self.log(f"   ❌ JavaScript mouseenter 也失败: {str(e2)[:100]}...")
                raise Exception(f"无法悬停下拉选项: {option_text}")

    def _execute_step_with_retry(self, page, step: Dict, max_retries: int = 3):
        """
        执行单个步骤，支持失败重试
        """
        action = step.get('action', '').lower()
        selector = step.get('selector', '')
        value = step.get('value', '')
        
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                self.step_screenshot = None
                self._execute_step_action(page, action, selector, value, step)
                return
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    self.log(f"   🔄 第 {attempt + 1} 次重试...")
                    page.wait_for_timeout(500)
        
        try:
            self.log("   📸 步骤失败，截图...")
            screenshot_bytes = page.screenshot(full_page=True)
            self.step_screenshot = base64.b64encode(screenshot_bytes).decode('utf-8')
            self.log("   ✅ 截图完成")
        except Exception as screenshot_error:
            self.log(f"   ⚠️ 截图失败: {str(screenshot_error)}")
            self.step_screenshot = None
        
        raise last_error

    def _execute_step_action(self, page, action: str, selector: Any, value: Any, step: Dict):
        """
        执行具体的步骤动作
        """
        locator = self._get_locator(page, selector)
        
        if action == 'click':
            if not selector:
                raise ValueError("Click 动作需要提供 selector")

            if self._is_in_el_select(locator):
                self.log(f"   检测到 el-select 组件内的元素...")
                self._click_el_select_trigger(page, locator)
            elif self._is_dropdown_option(locator):
                self.log(f"   检测到下拉框选项，使用特殊处理...")
                self._click_dropdown_option_v2(page, locator)
            else:
                self.log(f"   等待元素可见...")
                locator.wait_for(state='visible', timeout=10000)
                self.log(f"   点击元素")
                locator.click(timeout=10000)

            self.log("   ✅ 点击成功")

        elif action == 'double_click':
            if not selector:
                raise ValueError("Double click 动作需要提供 selector")
            self.log(f"   双击元素")
            locator.dblclick(timeout=10000)
            self.log("   ✅ 双击成功")

        elif action == 'right_click':
            if not selector:
                raise ValueError("Right click 动作需要提供 selector")
            self.log(f"   右键点击元素")
            locator.click(button='right', timeout=10000)
            self.log("   ✅ 右键点击成功")

        elif action == 'hover':
            if not selector:
                raise ValueError("Hover 动作需要提供 selector")

            is_dropdown_option = self._is_dropdown_option(locator)
            if is_dropdown_option:
                self.log(f"   检测到下拉框选项，使用特殊处理...")
                self._hover_dropdown_option(page, locator)
            else:
                self.log(f"   悬停元素")
                locator.hover(timeout=10000)
                self.log("   ✅ 悬停成功")

        elif action == 'fill':
            if not selector:
                raise ValueError("Fill 动作需要提供 selector")
            self.log(f"   填充输入框")
            locator.fill(str(value), timeout=10000)
            self.log(f"   ✅ 填充成功: {value}")

        elif action == 'select':
            if not selector:
                raise ValueError("Select 动作需要提供 selector")
            self.log(f"   选择下拉框选项: {value}")
            
            self.log(f"   点击下拉框打开选项列表...")
            locator.click(timeout=10000)
            self.log(f"   ✅ 下拉框已打开")
            
            self.log(f"   等待下拉选项列表...")
            try:
                dropdown_locator = page.locator('.el-select-dropdown, .el-dropdown-menu').first
                dropdown_locator.wait_for(state='visible', timeout=5000)
                self.log(f"   ✅ 下拉选项列表已出现")
            except Exception as e:
                self.log(f"   ⚠️ 等待下拉选项列表超时，继续尝试选择选项")
            
            self.log(f"   查找选项: {value}")
            try:
                option_locator = page.get_by_text(str(value), exact=False).filter(
                    has=page.locator('.el-select-dropdown__item, .el-dropdown-menu__item')
                ).first
                option_locator.wait_for(state='visible', timeout=5000)
                option_locator.click(timeout=10000)
                self.log(f"   ✅ 选择成功: {value}")
            except Exception as e:
                self.log(f"   ⚠️ 精确查找失败，尝试直接查找: {e}")
                option_locator = page.get_by_text(str(value), exact=False).first
                option_locator.click(timeout=10000)
                self.log(f"   ✅ 选择成功: {value}")

        elif action == 'wait':
            wait_time = int(value) if value else 1000
            self.log(f"   等待: {wait_time}ms")
            page.wait_for_timeout(wait_time)
            self.log("   ✅ 等待完成")

        elif action == 'scroll':
            if selector:
                self.log(f"   滚动元素")
                try:
                    scroll_data = json.loads(value) if value else {'scrollTop': 0, 'scrollLeft': 0}
                    locator.evaluate(f"""
                        el => {{
                            el.scrollTop = {scroll_data.get('scrollTop', 0)};
                            el.scrollLeft = {scroll_data.get('scrollLeft', 0)};
                        }}
                    """)
                    self.log("   ✅ 元素滚动成功")
                except Exception as e:
                    self.log(f"   ⚠️ 元素滚动失败: {e}")
            else:
                scroll_amount = int(value) if value else 500
                self.log(f"   滚动页面: {scroll_amount}px")
                page.mouse.wheel(0, scroll_amount)
                self.log("   ✅ 页面滚动成功")

        elif action == 'drag_and_drop':
            if not selector:
                raise ValueError("Drag and drop 动作需要提供 selector (源元素)")
            if not value:
                raise ValueError("Drag and drop 动作需要提供 value (目标选择器)")
            self.log(f"   拖拽元素: {selector} -> {value}")
            
            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass
            
            page.wait_for_timeout(1000)
            
            source = self._get_locator(page, selector)
            target = self._get_locator(page, value)
            
            try:
                source.wait_for(state='visible', timeout=15000)
                target.wait_for(state='visible', timeout=15000)
            except Exception as e:
                self.log(f"   ⚠️ 等待元素超时，尝试查找备选选择器")
                import re
                
                if ':has-text(' in selector:
                    text_match = re.search(r':has-text\("([^"]+)"\)', selector)
                    if text_match:
                        text = text_match.group(1)
                        self.log(f"   尝试使用文本查找源元素: {text}")
                        try:
                            source = page.get_by_text(text, exact=False).first
                            source.wait_for(state='visible', timeout=10000)
                        except:
                            source = page.locator(f'text={text}').first
                            source.wait_for(state='visible', timeout=10000)
                
                if ':has-text(' in value:
                    text_match = re.search(r':has-text\("([^"]+)"\)', value)
                    if text_match:
                        text = text_match.group(1)
                        self.log(f"   尝试使用文本查找目标元素: {text}")
                        try:
                            target = page.get_by_text(text, exact=False).first
                            target.wait_for(state='visible', timeout=10000)
                        except:
                            target = page.locator(f'text={text}').first
                            target.wait_for(state='visible', timeout=10000)
                
                if not source.is_visible() or not target.is_visible():
                    raise
            
            source.drag_to(target, timeout=15000)
            self.log("   ✅ 拖拽成功")

        elif action == 'screenshot':
            self.log("   📸 截图")

        else:
            self.log(f"   ⚠️ 未知动作类型: {action}")

    def run_ui_case(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行 UI 测试用例
        """
        self.logs = []
        screenshot_base64 = None
        self.step_screenshot = None
        step_screenshots = []

        temp_dir = self._setup_temp_dir()
        self.log(f"📁 临时目录: {temp_dir}")

        try:
            with sync_playwright() as p:
                self.log("🚀 启动 Chromium 浏览器...")

                launch_args = [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disk-cache-dir=' + temp_dir,
                ]

                try:
                    browser = p.chromium.launch(
                        headless=True,
                        args=launch_args,
                        downloads_path=temp_dir,
                    )
                except Exception as launch_error:
                    self.log(f"⚠️ 首次启动失败，尝试备用配置: {str(launch_error)}")
                    browser = p.chromium.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox'],
                    )

                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=True,
                )
                page = context.new_page()

                url = case_data.get('url', '')
                if not url:
                    return {
                        'success': False,
                        'screenshot': None,
                        'logs': self.logs,
                        'error': '未提供起始 URL'
                    }
                
                url = url.strip()
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url

                self.log(f"📍 导航到: {url}")
                page.goto(url, wait_until='networkidle', timeout=30000)
                self.log("✅ 页面加载完成")

                steps = case_data.get('steps', [])
                for index, step in enumerate(steps, 1):
                    action = step.get('action', '').lower()
                    selector = step.get('selector', '')
                    value = step.get('value', '')

                    self.log(f"\n📝 步骤 {index}: {action}")

                    try:
                        self._execute_step_with_retry(page, step)
                        
                        page.wait_for_timeout(500)
                        self.log("   ⏳ 等待页面加载...")
                        try:
                            page.wait_for_load_state('networkidle', timeout=5000)
                            self.log("   ✅ 页面加载完成")
                        except:
                            pass
                        
                        try:
                            self.log(f"   📸 步骤 {index} 截图...")
                            screenshot_bytes = page.screenshot(full_page=True)
                            self.step_screenshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                            step_screenshots.append({
                                'step': index,
                                'screenshot': f"data:image/png;base64,{self.step_screenshot}"
                            })
                            self.log(f"   ✅ 步骤 {index} 截图完成")
                        except Exception as screenshot_error:
                            self.log(f"   ⚠️ 步骤截图失败: {screenshot_error}")

                    except Exception as e:
                        error_msg = str(e)
                        self.log(f"\n❌ 错误: {error_msg}")
                        
                        if self.step_screenshot:
                            self.log(f"📸 使用步骤 {index - 1} 的截图")
                        else:
                            try:
                                self.log("   📸 步骤失败，截图...")
                                screenshot_bytes = page.screenshot(full_page=True)
                                self.step_screenshot = base64.b64encode(screenshot_bytes).decode('utf-8')
                                self.log("   ✅ 截图完成")
                            except:
                                pass
                        
                        context.close()
                        browser.close()
                        self.log("🛑 浏览器已关闭")
                        
                        return {
                            'success': False,
                            'screenshot': f"data:image/png;base64,{self.step_screenshot}" if self.step_screenshot else None,
                            'step_screenshots': step_screenshots,
                            'logs': self.logs,
                            'error': error_msg
                        }

                self.log("\n⏳ 等待页面显示结果...")
                page.wait_for_timeout(1500)
                
                self.log("📸 正在截图...")
                screenshot_bytes = page.screenshot(full_page=True)
                screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                self.log("✅ 截图完成")

                context.close()
                browser.close()
                self.log("🛑 浏览器已关闭")

                return {
                    'success': True,
                    'screenshot': f"data:image/png;base64,{screenshot_base64}",
                    'step_screenshots': step_screenshots,
                    'logs': self.logs,
                    'error': None
                }

        except Exception as e:
            error_msg = str(e)
            self.log(f"\n❌ 错误: {error_msg}")
            logger.error(f"Playwright 运行错误: {error_msg}")

            if 'EPERM' in error_msg or 'operation not permitted' in error_msg:
                error_msg = (
                    "浏览器启动失败（权限问题）。\n"
                    "建议解决方案:\n"
                    "1. 以管理员身份运行后端服务\n"
                    "2. 检查杀毒软件是否阻止了浏览器启动\n"
                    "3. 手动安装 Playwright 浏览器: playwright install chromium"
                )
            elif "executable doesn't exist" in error_msg.lower():
                error_msg = (
                    "Chromium 浏览器未安装。\n"
                    "请运行: playwright install chromium"
                )

            return {
                'success': False,
                'screenshot': f"data:image/png;base64,{self.step_screenshot}" if self.step_screenshot else None,
                'step_screenshots': step_screenshots,
                'logs': self.logs,
                'error': error_msg
            }

        finally:
            self._cleanup_temp_dir()


def run_ui_case(case_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    便捷函数：运行 UI 测试用例
    """
    runner = PlaywrightRunner()
    return runner.run_ui_case(case_data)
