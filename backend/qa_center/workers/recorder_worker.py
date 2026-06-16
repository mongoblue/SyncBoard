"""
Recorder Worker — 子进程运行录制会话。
stdin 持续接收命令（JSON Lines），stdout 流式输出事件（JSON Lines）。
"""
import sys
import json
import os
import tempfile
import traceback
import logging
from threading import Event


def _setup_io_logging():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="[recorder] %(levelname)s %(message)s",
        stream=sys.stderr,
    )


logger = logging.getLogger("recorder_worker")


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def read_command() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError("stdin closed")
    return json.loads(line)


def setup_temp_dir() -> str:
    base = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", ".playwright-temp"
    ))
    os.makedirs(base, exist_ok=True)
    td = tempfile.mkdtemp(prefix="rec_", dir=base)
    os.environ["TEMP"] = td
    os.environ["TMP"] = td
    os.environ["PLAYWRIGHT_TEMP_DIR"] = td
    return td


def cleanup_temp_dir(td: str) -> None:
    import shutil
    if td and os.path.exists(td):
        shutil.rmtree(td, ignore_errors=True)


# === 录制脚本（从 utils/recorder.py 的 PlaywrightRecorder.RECORDING_SCRIPT 复制） ===
RECORDING_SCRIPT = r"""
    (function() {
        console.log('[Recorder] Script injected - v5 Playwright Expert Edition');
        
        let lastEventStr = '';
        let lastEventTime = 0;
        
        // ==================== 断言录制功能 ====================
        let isAssertMode = false;
        
        // 创建悬浮工具栏
        function createAssertToolbar() {
            // 如果已存在则不重复创建
            if (document.getElementById('recorder-assert-toolbar')) {
                return;
            }
            
            // 创建工具栏容器
            const toolbar = document.createElement('div');
            toolbar.id = 'recorder-assert-toolbar';
            toolbar.innerHTML = `
                <style>
                    #recorder-assert-toolbar {
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        z-index: 2147483647;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    }
                    #recorder-assert-toolbar .assert-btn {
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        border: none;
                        padding: 12px 20px;
                        border-radius: 25px;
                        font-size: 14px;
                        font-weight: 600;
                        cursor: pointer;
                        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                        transition: all 0.3s ease;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                    }
                    #recorder-assert-toolbar .assert-btn:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
                    }
                    #recorder-assert-toolbar .assert-btn.active {
                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                        animation: pulse 1.5s infinite;
                    }
                    @keyframes pulse {
                        0% { box-shadow: 0 0 0 0 rgba(245, 87, 108, 0.7); }
                        70% { box-shadow: 0 0 0 10px rgba(245, 87, 108, 0); }
                        100% { box-shadow: 0 0 0 0 rgba(245, 87, 108, 0); }
                    }
                    body.recorder-assert-cursor {
                        cursor: crosshair !important;
                    }
                    body.recorder-assert-cursor * {
                        cursor: crosshair !important;
                    }
                </style>
                <button class="assert-btn" id="recorder-assert-btn">
                    <span>🎯</span>
                    <span>验证元素 (Assert)</span>
                </button>
            `;
            document.body.appendChild(toolbar);
            
            // 绑定按钮点击事件
            const btn = document.getElementById('recorder-assert-btn');
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleAssertMode();
            });
            
            console.log('[Recorder] Assert toolbar created');
        }
        
        // 切换断言模式
        function toggleAssertMode() {
            isAssertMode = !isAssertMode;
            const btn = document.getElementById('recorder-assert-btn');
            
            if (isAssertMode) {
                document.body.classList.add('recorder-assert-cursor');
                btn.classList.add('active');
                btn.innerHTML = '<span>⏹️</span><span>退出验证</span>';
                console.log('[Recorder] Assert mode: ON');
            } else {
                exitAssertMode();
            }
        }
        
        // 退出断言模式
        function exitAssertMode() {
            isAssertMode = false;
            document.body.classList.remove('recorder-assert-cursor');
            const btn = document.getElementById('recorder-assert-btn');
            if (btn) {
                btn.classList.remove('active');
                btn.innerHTML = '<span>🎯</span><span>验证元素 (Assert)</span>';
            }
            console.log('[Recorder] Assert mode: OFF');
        }
        
        // 简易的 CSS 选择器生成函数
        function getCssSelector(el) {
            const tag = el.tagName.toLowerCase();
            
            // 1. 优先使用 data-testid
            if (el.dataset && el.dataset.testid) {
                return `[data-testid="${el.dataset.testid}"]`;
            }
            
            // 2. 使用稳定的 ID
            if (el.id && !el.id.match(/^el-id-\d+-\d+$/) && !el.id.match(/^[a-f0-9]{8,}$/i)) {
                return '#' + el.id;
            }
            
            // 3. 对于输入框，使用 placeholder 或 name
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                if (el.placeholder) {
                    return `[placeholder="${el.placeholder}"]`;
                }
                if (el.getAttribute('aria-label')) {
                    return `[aria-label="${el.getAttribute('aria-label')}"]`;
                }
                if (el.name) {
                    return `[name="${el.name}"]`;
                }
            }
            
            // 4. 对于按钮，使用文本
            if (tag === 'button') {
                const text = el.textContent ? el.textContent.trim().substring(0, 20) : '';
                if (text) {
                    return `button:has-text("${text}")`;
                }
                if (el.getAttribute('aria-label')) {
                    return `button[aria-label="${el.getAttribute('aria-label')}"]`;
                }
            }
            
            // 5. 对于链接，使用文本
            if (tag === 'a') {
                const text = el.textContent ? el.textContent.trim().substring(0, 20) : '';
                if (text) {
                    return `a:has-text("${text}")`;
                }
            }
            
            // 6. 对于其他元素，使用文本
            const text = el.textContent ? el.textContent.trim().substring(0, 30) : '';
            if (text && text.length > 0 && text.length < 50) {
                return `${tag}:has-text("${text}")`;
            }
            
            // 7. 使用父元素上下文
            const parent = el.parentElement;
            if (parent) {
                const parentText = parent.textContent ? parent.textContent.trim().substring(0, 20) : '';
                if (parentText && parentText.length > 0) {
                    return `:has-text("${parentText}") >> ${tag}`;
                }
                if (parent.id && !parent.id.match(/^el-id-\d+-\d+$/)) {
                    return `#${parent.id} ${tag}`;
                }
            }
            
            return tag;
        }
        
        // 处理断言事件
        function handleAssertEvent(target) {
            // 获取元素文本内容
            const text = target.textContent ? target.textContent.trim() : '';
            
            // 获取 CSS 选择器
            const selector = getCssSelector(target);
            
            // 生成 Playwright 断言代码
            let assertCode = '';
            if (text && text.length > 0 && text.length < 100) {
                assertCode = `expect(page.locator('${selector}')).toHaveText('${text}')`;
            } else {
                // 如果没有文本，生成检查元素存在的断言
                assertCode = `expect(page.locator('${selector}')).toBeVisible()`;
            }
            
            console.log('%c[Recorder Assert] ' + assertCode, 'color: #10b981; font-weight: bold; font-size: 14px;');
            
            // 发送断言事件到后端
            sendAssertEvent({
                action: 'assert',
                selector: selector,
                expectedText: text,
                assertCode: assertCode
            });
            
            // 退出断言模式
            exitAssertMode();
        }
        
        // 发送断言事件
        function sendAssertEvent(data) {
            console.log('[Recorder Assert] Sending:', data);
            if (window.onRecordAssertEvent) {
                window.onRecordAssertEvent(data);
            }
        }
        
        // 初始化工具栏
        createAssertToolbar();
        
        // ==================== Playwright Expert 选择器生成器 ====================
        // 优先级: 1. Role-based > 2. Text-based > 3. Test ID > 4. CSS
        
        function getElementInfo(el) {
            const tag = el.tagName.toLowerCase();
            const text = el.textContent ? el.textContent.trim().substring(0, 50) : '';
            
            // 获取 placeholder，优先使用 el.placeholder，否则使用 getAttribute
            const placeholder = el.placeholder || el.getAttribute('placeholder') || '';
            
            return {
                tag,
                text,
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                title: el.getAttribute('title'),
                placeholder: placeholder,
                testId: el.dataset?.testid,
                id: el.id,
                name: el.name,
                className: el.className
            };
        }
        
        function getPlaywrightSelector(el) {
            const info = getElementInfo(el);
            const selectors = {
                role: null,
                text: null,
                testId: null,
                css: null
            };
            
            // ========== 1. Role-based 选择器 (最优先) ==========
            // 根据 HTML 语义或 ARIA role 确定元素角色
            let role = info.role;
            let name = info.ariaLabel || info.title || info.text;
            
            // 根据标签推断 role
            if (!role) {
                switch(info.tag) {
                    case 'button': role = 'button'; break;
                    case 'a': role = 'link'; break;
                    case 'input':
                        if (el.type === 'text' || el.type === 'email' || el.type === 'password') {
                            role = 'textbox';
                        } else if (el.type === 'checkbox') {
                            role = 'checkbox';
                        } else if (el.type === 'radio') {
                            role = 'radio';
                        }
                        break;
                    case 'select': role = 'combobox'; break;
                    case 'textarea': role = 'textbox'; break;
                    case 'li':
                        // 检查是否在菜单中
                        if (isInDropdown(el)) {
                            role = 'menuitem';
                        } else {
                            role = 'listitem';
                        }
                        break;
                    case 'nav': role = 'navigation'; break;
                    case 'main': role = 'main'; break;
                    case 'header': role = 'banner'; break;
                    case 'footer': role = 'contentinfo'; break;
                    case 'article': role = 'article'; break;
                }
            }
            
            // 生成 role-based 选择器
            // 对于有 name 的元素，使用 role + name
            if (role && name) {
                selectors.role = { role, name };
            }
            // 对于 input 元素，使用 placeholder 或 name 属性作为 name
            else if (role === 'textbox' && info.tag === 'input') {
                const inputName = info.placeholder || info.name || '';
                selectors.role = { role: 'textbox', name: inputName };
            }
            // 对于 Icon 按钮（button 元素但没有文本），仍然使用 role
            else if (role === 'button' && info.tag === 'button') {
                selectors.role = { role: 'button', name: '' };
            }
            
            // ========== 2. Text-based 选择器 (次优先) ==========
            if (info.text && info.text.length > 0 && info.text.length < 50) {
                // 过滤掉过长的文本
                selectors.text = info.text;
            }
            
            // ========== 3. Test ID 选择器 ==========
            if (info.testId) {
                selectors.testId = info.testId;
            }
            
            // ========== 4. CSS 选择器 (最后手段) ==========
            selectors.css = getCssSelector(el);
            
            return selectors;
        }
        
        // 检查元素是否在下拉菜单中
        function isInDropdown(el) {
            let parent = el.parentElement;
            let depth = 0;
            while (parent && depth < 5) {
                const className = parent.className || '';
                if (className.includes('dropdown') || 
                    className.includes('menu') ||
                    className.includes('el-dropdown') ||
                    className.includes('el-select') ||
                    className.includes('el-cascader')) {
                    return true;
                }
                parent = parent.parentElement;
                depth++;
            }
            return false;
        }
        
        function getCssSelector(el) {
            const tag = el.tagName.toLowerCase();
            const text = el.textContent ? el.textContent.trim() : '';
            
            // ========== 【改进】对于 dialog/modal，使用 role 或标题 ==========
            const role = el.getAttribute('role');
            if (role === 'dialog' || role === 'alertdialog') {
                // 优先使用 aria-labelledby 指向的标题
                const labelledBy = el.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const titleEl = document.getElementById(labelledBy);
                    if (titleEl) {
                        const titleText = titleEl.textContent.trim();
                        if (titleText) {
                            return `[role="dialog"]:has-text("${titleText}")`;
                        }
                    }
                }
                // 使用 dialog 内的标题文本
                const heading = el.querySelector('h1, h2, h3, h4, h5, h6, .dialog-title, .modal-title');
                if (heading) {
                    const headingText = heading.textContent.trim();
                    if (headingText) {
                        return `[role="dialog"]:has-text("${headingText}")`;
                    }
                }
                // 使用 dialog 内的任何文本
                if (text && text.length > 0 && text.length < 100) {
                    return `[role="dialog"]:has-text("${text.substring(0, 50)}")`;
                }
                return '[role="dialog"]';
            }
            
            // ========== 1. 优先使用 data-testid ==========
            if (el.dataset && el.dataset.testid) {
                return `[data-testid="${el.dataset.testid}"]`;
            }
            
            // ========== 2. 使用稳定的 ID ==========
            if (el.id && !el.id.match(/^el-id-\d+-\d+$/) && !el.id.match(/^[a-f0-9]{8,}$/i)) {
                return '#' + el.id;
            }
            
            // ========== 3. 对于输入框，使用 placeholder 或 name 或 aria-label ==========
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                // 优先使用 placeholder（最稳定）
                if (el.placeholder) {
                    return `[placeholder="${el.placeholder}"]`;
                }
                // 其次使用 aria-label
                if (el.getAttribute('aria-label')) {
                    return `[aria-label="${el.getAttribute('aria-label')}"]`;
                }
                // 然后使用 name
                if (el.name) {
                    return `[name="${el.name}"]`;
                }

                // 【简化】只检查直接父元素
                const parent = el.parentElement;
                if (parent) {
                    // 检查父元素内是否有 label
                    const label = parent.querySelector('label');
                    if (label) {
                        const labelText = label.textContent.trim();
                        if (labelText) {
                            return `:has-text("${labelText}") >> ${tag}`;
                        }
                    }

                    // 检查父元素的前一个兄弟是否是 label
                    const prevSibling = parent.previousElementSibling;
                    if (prevSibling && prevSibling.tagName.toLowerCase() === 'label') {
                        const labelText = prevSibling.textContent.trim();
                        if (labelText) {
                            return `:has-text("${labelText}") >> ${tag}`;
                        }
                    }

                    // 使用父元素的 id 或 class
                    if (parent.id && !parent.id.match(/^el-id-\d+-\d+$/)) {
                        return `#${parent.id} ${tag}`;
                    }

                    // 【禁用】使用父元素的 class
                    // const parentClass = parent.className;
                    // if (parentClass && typeof parentClass === 'string') {
                    //     const classes = parentClass.split(' ').filter(c =>
                    //         c && !c.match(/^el-/) && !c.match(/^is-/) && c.length > 3
                    //     );
                    //     if (classes.length > 0) {
                    //         return `.${classes[0]} ${tag}`;
                    //     }
                    // }

                    // 使用父元素文本
                    const parentText = parent.textContent ?
                        parent.textContent.trim().substring(0, 30) : '';
                    if (parentText && parentText.length > 0) {
                        return `:has-text("${parentText}") >> ${tag}`;
                    }
                }
            }
            
            // ========== 4. 对于按钮，使用 text + type（如果有） ==========
            if (tag === 'button') {
                const btnText = text.substring(0, 20);
                if (btnText) {
                    if (el.type && el.type !== 'button') {
                        return `button[type="${el.type}"]:has-text("${btnText}")`;
                    }
                    return `button:has-text("${btnText}")`;
                }
                // 如果没有文本，尝试使用 aria-label 或 title
                if (el.getAttribute('aria-label')) {
                    return `button[aria-label="${el.getAttribute('aria-label')}"]`;
                }
                if (el.title) {
                    return `button[title="${el.title}"]`;
                }
                // 【修复】对于 Icon 按钮（没有文本），使用稳定的 class
                if (el.className && typeof el.className === 'string') {
                    const classes = el.className.split(' ').filter(c =>
                        c && !c.match(/^el-/) && c.length > 3
                    );
                    if (classes.length > 0) {
                        return `button.${classes[0]}`;
                    }
                }
                // 【修复】使用父元素的文本作为上下文
                const parent = el.parentElement;
                if (parent) {
                    const parentText = parent.textContent ?
                        parent.textContent.trim().substring(0, 30) : '';
                    if (parentText && parentText.length > 0) {
                        return `:has-text("${parentText}") >> button`;
                    }
                }
            }
            
            // ========== 5. 对于链接，使用 text ==========
            if (tag === 'a') {
                const linkText = text.substring(0, 20);
                if (linkText) {
                    return `a:has-text("${linkText}")`;
                }
            }
            
            // ========== 6. 对于 heading，使用 text ==========
            if (tag.match(/^h[1-6]$/)) {
                const headingText = text.substring(0, 30);
                if (headingText) {
                    return `${tag}:has-text("${headingText}")`;
                }
            }
            
            // ========== 7. 对于下拉菜单项，使用 text ==========
            if (tag === 'li' || isInDropdown(el)) {
                const liText = text.substring(0, 30);
                if (liText) {
                    // 使用更通用的选择器，不限于 li 标签
                    return `:has-text("${liText}")`;
                }
            }
            
            // ========== 8. 对于其他元素，必须使用 text ==========
            // 禁止使用任何宽泛的 class 选择器（如 .project-name）
            if (text && text.length > 0 && text.length < 50) {
                return `${tag}:has-text("${text}")`;
            }

            // ========== 9. 如果没有任何文本，尝试使用稳定的 class 或父元素上下文（简化版） ==========
            // 只检查一层父元素，避免过多 DOM 查询

            const parent = el.parentElement;
            if (parent) {
                // 优先使用父元素的文本
                const parentText = parent.textContent ?
                    parent.textContent.trim().substring(0, 30) : '';
                if (parentText && parentText.length > 0 && parentText !== text) {
                    return `:has-text("${parentText}") >> ${tag}`;
                }

                // 使用父元素的稳定 class
                if (parent.className && typeof parent.className === 'string') {
                    const parentClasses = parent.className.split(' ').filter(c =>
                        c && !c.match(/^el-/) && c.length > 3
                    );
                    if (parentClasses.length > 0) {
                        return `.${parentClasses[0]} ${tag}`;
                    }
                }

                // 使用父元素的 id
                if (parent.id && !parent.id.match(/^el-id-\d+-\d+$/)) {
                    return `#${parent.id} ${tag}`;
                }
            }

            // 【改进】尝试使用元素自身的稳定 class（允许业务类名，禁用框架/动态类名）
            if (el.className && typeof el.className === 'string') {
                // 定义稳定的业务类名关键词
                const stableKeywords = /(btn|button|add|create|new|submit|save|delete|remove|edit|update|dialog|modal|card|item|list|menu|nav|header|footer|content|main|sidebar|wrapper|container|box)/i;
                // 定义禁用的框架/动态类名前缀
                const forbiddenPrefixes = /^(el-|is-|has-|active|selected|focused|disabled|hover|focus|checked|open|show|hidden|visible|expanded|collapsed)/i;
                
                const classes = el.className.split(' ').filter(c =>
                    c && 
                    !forbiddenPrefixes.test(c) &&
                    stableKeywords.test(c) &&
                    c.length > 3
                );
                if (classes.length > 0) {
                    return `.${classes[0]}`;
                }
            }

            // 返回空字符串让上层知道需要特殊处理
            return '';
        }
        
        // 【改进】向上查找父元素的选择器
        function getParentSelector(el) {
            let parent = el.parentElement;
            let depth = 0;
            
            while (parent && depth < 3) {
                const parentTag = parent.tagName.toLowerCase();
                
                // 如果父元素是 button，优先使用 button 的选择器
                if (parentTag === 'button') {
                    // 尝试获取 button 的 aria-label 或 title
                    const ariaLabel = parent.getAttribute('aria-label');
                    if (ariaLabel) {
                        return { type: 'css', css: `button[aria-label="${ariaLabel}"]` };
                    }
                    
                    const title = parent.getAttribute('title');
                    if (title) {
                        return { type: 'css', css: `button[title="${title}"]` };
                    }
                    
                    // 使用 button 的文本
                    const btnText = parent.textContent ? parent.textContent.trim().substring(0, 20) : '';
                    if (btnText) {
                        return { type: 'css', css: `button:has-text("${btnText}")` };
                    }
                    
                    // 【改进】如果 button 没有文本，使用祖父元素的文本作为上下文
                    const grandparent = parent.parentElement;
                    if (grandparent) {
                        const grandparentText = grandparent.textContent ?
                            grandparent.textContent.trim().substring(0, 30) : '';
                        if (grandparentText && grandparentText.length > 0) {
                            return { type: 'css', css: `:has-text("${grandparentText}") >> button` };
                        }
                    }
                    
                    // 【改进】使用 button 的稳定类名（允许业务类名）
                    if (parent.className && typeof parent.className === 'string') {
                        const stableKeywords = /(btn|button|add|create|new|submit|save|delete|remove|edit|update|dialog|modal|card|item|list|menu|nav|header|footer|content|main|sidebar|wrapper|container|box)/i;
                        const forbiddenPrefixes = /^(el-|is-|has-|active|selected|focused|disabled|hover|focus|checked|open|show|hidden|visible|expanded|collapsed)/i;
                        
                        const classes = parent.className.split(' ').filter(c =>
                            c && 
                            !forbiddenPrefixes.test(c) &&
                            stableKeywords.test(c) &&
                            c.length > 3
                        );
                        if (classes.length > 0) {
                            return { type: 'css', css: `button.${classes[0]}` };
                        }
                    }
                    
                    // 【最后手段】使用 button 标签，但添加警告
                    console.log('[Recorder] Warning: Using generic "button" selector, consider adding aria-label to the button');
                    return { type: 'css', css: 'button' };
                }
                
                // 如果父元素有稳定的 id 或 class，使用它作为上下文
                if (parent.id && !parent.id.match(/^el-id-\d+-\d+$/)) {
                    return { type: 'css', css: `#${parent.id}` };
                }
                
                // 【禁用】使用父元素的 class
                // if (parent.className && typeof parent.className === 'string') {
                //     const classes = parent.className.split(' ').filter(c =>
                //         c && !c.match(/^el-/) && !c.match(/^is-/) && c.length > 3
                //     );
                //     if (classes.length > 0) {
                //         return { type: 'css', css: `.${classes[0]}` };
                //     }
                // }
                
                // 使用父元素的文本作为上下文
                const parentText = parent.textContent ?
                    parent.textContent.trim().substring(0, 30) : '';
                if (parentText && parentText.length > 0) {
                    return { type: 'css', css: `:has-text("${parentText}")` };
                }
                
                parent = parent.parentElement;
                depth++;
            }
            
            return null;
        }
        
        // 获取最精确的选择器（优先使用 role/text，避免简单标签）
        function getBestSelector(el) {
            const selectors = getPlaywrightSelector(el);
            
            // 优先返回 role-based 选择器
            if (selectors.role) {
                return {
                    type: 'role',
                    role: selectors.role.role,
                    name: selectors.role.name,
                    css: selectors.css  // 备选
                };
            }
            
            // 其次返回 text-based 选择器
            if (selectors.text) {
                return {
                    type: 'text',
                    text: selectors.text,
                    css: selectors.css
                };
            }
            
            // 然后 test ID
            if (selectors.testId) {
                return {
                    type: 'testId',
                    testId: selectors.testId,
                    css: selectors.css
                };
            }
            
            // 【改进】如果 CSS 为空，尝试向上查找父元素
            if (!selectors.css || selectors.css === '') {
                console.log('[Recorder] CSS selector is empty, trying parent element...');
                const parentSelector = getParentSelector(el);
                if (parentSelector) {
                    console.log('[Recorder] Using parent selector:', parentSelector);
                    return parentSelector;
                }
            }
            
            // 最后 CSS
            return {
                type: 'css',
                css: selectors.css
            };
        }

        // fill 操作的防抖处理
        let fillDebounceTimer = null;
        let lastFillSelector = '';
        
        function sendEvent(data) {
            // 生成指纹
            const currentEventStr = JSON.stringify(data);
            const now = Date.now();
            
            // 强力去重：如果内容完全一样，且间隔小于 500ms，丢弃
            if (currentEventStr === lastEventStr && (now - lastEventTime < 500)) {
                console.log('[Recorder] Filtered duplicate:', data);
                return;
            }
            
            // 对于 fill 操作，使用防抖避免短时间内多次发送
            if (data.action === 'fill') {
                const selectorKey = data.selector && typeof data.selector === 'object' 
                    ? (data.selector.css || JSON.stringify(data.selector)) 
                    : String(data.selector);
                
                // 如果是同一个输入框的 fill，延迟发送
                if (selectorKey === lastFillSelector) {
                    clearTimeout(fillDebounceTimer);
                    fillDebounceTimer = setTimeout(() => {
                        lastEventStr = currentEventStr;
                        lastEventTime = Date.now();
                        console.log('[Recorder] Sending (debounced):', data);
                        window.onRecordEvent(data);
                    }, 300);
                    return;
                }
                lastFillSelector = selectorKey;
            }
            
            lastEventStr = currentEventStr;
            lastEventTime = now;
            
            console.log('[Recorder] Sending:', data);
            window.onRecordEvent(data);
        }
        
        // ==================== 事件监听 ====================

        // 监听点击
        document.addEventListener('click', function(e) {
            // 排除工具栏自身的点击
            if (e.target.closest('#recorder-overlay')) return;
            if (e.target.closest('#recorder-assert-toolbar')) return;
            
            // ========== 断言模式处理 ==========
            if (isAssertMode) {
                // 阻止默认行为和冒泡
                e.preventDefault();
                e.stopPropagation();
                
                let target = e.target;
                const tag = target.tagName.toLowerCase();
                
                // 如果点击的是内联元素，向上查找可交互的父元素
                const inlineTags = ['span', 'i', 'em', 'strong', 'b', 'svg', 'path', 'circle',
                                    'rect', 'g', 'use', 'polygon', 'polyline', 'line', 'ellipse',
                                    'img', 'font-awesome-icon'];
                
                if (inlineTags.includes(tag) || target.closest('svg') || target.closest('[class*="icon"]')) {
                    let parent = target.parentElement;
                    let depth = 0;
                    while (parent && depth < 5) {
                        const parentTag = parent.tagName.toLowerCase();
                        if (['button', 'a', 'label'].includes(parentTag) ||
                            parent.getAttribute('role') === 'button' ||
                            parent.getAttribute('role') === 'link' ||
                            parent.classList.contains('el-button') ||
                            window.getComputedStyle(parent).cursor === 'pointer') {
                            target = parent;
                            break;
                        }
                        parent = parent.parentElement;
                        depth++;
                    }
                }
                
                // 处理断言事件
                handleAssertEvent(target);
                return;
            }
            
            // ========== 普通录制模式 ==========
            let target = e.target;
            const tag = target.tagName.toLowerCase();
            
            // 忽略 input/textarea 的点击（fill 会自动 focus）
            if (tag === 'input' || tag === 'textarea') {
                console.log('[Recorder] Ignored click on input');
                return;
            }
            
            // 如果点击的是 span/i/svg 等内联元素，向上查找到可交互的父元素
            const inlineTags = ['span', 'i', 'em', 'strong', 'b', 'svg', 'path', 'circle',
                                'rect', 'g', 'use', 'polygon', 'polyline', 'line', 'ellipse',
                                'img', 'font-awesome-icon', 'i[class*="icon"]'];

            if (inlineTags.includes(tag) || target.closest('svg') || target.closest('[class*="icon"]')) {
                let parent = target.parentElement;
                let depth = 0;
                while (parent && depth < 5) {
                    const parentTag = parent.tagName.toLowerCase();
                    // 查找可交互元素或带有特定 role/样式的元素
                    if (['button', 'a', 'label'].includes(parentTag) ||
                        parent.getAttribute('role') === 'button' ||
                        parent.getAttribute('role') === 'link' ||
                        parent.classList.contains('el-button') ||
                        parent.classList.contains('clickable') ||
                        parent.onclick ||
                        window.getComputedStyle(parent).cursor === 'pointer') {
                        target = parent;
                        console.log('[Recorder] Found parent interactive element for click:', parentTag);
                        break;
                    }
                    parent = parent.parentElement;
                    depth++;
                }
            }

            const selector = getBestSelector(target);
            
            sendEvent({
                action: 'click',
                selector: selector,
                value: ''
            });
        }, true);
        
        // 监听双击
        document.addEventListener('dblclick', function(e) {
            if (e.target.closest('#recorder-overlay')) return;
            if (e.target.closest('#recorder-assert-toolbar')) return;
            
            sendEvent({
                action: 'double_click',
                selector: getBestSelector(e.target),
                value: ''
            });
        }, true);
        
        // 监听右键
        document.addEventListener('contextmenu', function(e) {
            if (e.target.closest('#recorder-overlay')) return;
            if (e.target.closest('#recorder-assert-toolbar')) return;
            
            sendEvent({
                action: 'right_click',
                selector: getBestSelector(e.target),
                value: ''
            });
        }, true);
        
        // 监听鼠标悬停（带防抖）
        let hoverTimeout = null;
        let lastHoverTarget = null;
        document.addEventListener('mouseover', function(e) {
            if (e.target.closest('#recorder-overlay')) return;
            if (e.target.closest('#recorder-assert-toolbar')) return;
            
            clearTimeout(hoverTimeout);
            const target = e.target;
            
            if (target === lastHoverTarget) return;
            
            hoverTimeout = setTimeout(() => {
                const hasDropdown = target.querySelector('[class*="dropdown"], [class*="menu"]') ||
                                     target.closest('[class*="dropdown"], [class*="menu"]');
                
                if (hasDropdown || target.getAttribute('data-tooltip') || target.title) {
                    sendEvent({
                        action: 'hover',
                        selector: getBestSelector(target),
                        value: ''
                    });
                    lastHoverTarget = target;
                }
            }, 500);
        }, true);

        // 监听输入 - 使用 change 事件记录最终值（在失去焦点或回车时触发）
        document.addEventListener('change', function(e) {
            const target = e.target;
            const tag = target.tagName.toLowerCase();
            
            if (tag === 'input' || tag === 'textarea') {
                const currentValue = target.value || '';
                
                // 只在值不为空时记录
                if (currentValue.length > 0) {
                    sendEvent({
                        action: 'fill',
                        selector: getBestSelector(target),
                        value: currentValue
                    });
                }
            }
        }, true);
        
        // 监听 select 下拉框变化
        document.addEventListener('change', function(e) {
            const target = e.target;
            const tag = target.tagName.toLowerCase();
            
            if (tag === 'select') {
                const selectedOption = target.options[target.selectedIndex];
                sendEvent({
                    action: 'select',
                    selector: getBestSelector(target),
                    value: target.value,
                    optionText: selectedOption ? selectedOption.text : ''
                });
            }
        }, true);

        // 监听键盘事件
        document.addEventListener('keydown', function(e) {
            const specialKeys = ['Enter', 'Escape', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'];
            
            if (specialKeys.includes(e.key)) {
                sendEvent({
                    action: 'keydown',
                    selector: getBestSelector(e.target),
                    value: e.key,
                    modifiers: {
                        ctrl: e.ctrlKey,
                        alt: e.altKey,
                        shift: e.shiftKey,
                        meta: e.metaKey
                    }
                });
            }
        }, true);
        
        // 监听滚动（防抖）
        let scrollDebounceTimer = null;
        window.addEventListener('scroll', function(e) {
            clearTimeout(scrollDebounceTimer);
            scrollDebounceTimer = setTimeout(() => {
                const scrollTarget = e.target === document ? window : e.target;
                
                if (scrollTarget !== window) {
                    sendEvent({
                        action: 'scroll',
                        selector: getBestSelector(scrollTarget),
                        value: JSON.stringify({
                            scrollTop: scrollTarget.scrollTop,
                            scrollLeft: scrollTarget.scrollLeft
                        })
                    });
                }
            }, 500);
        }, true);

        // 监听拖拽事件
        (function() {
            let dragSource = null;
            let dragSourceSelector = '';

            document.addEventListener('dragstart', function(e) {
                dragSource = e.target;
                dragSourceSelector = getBestSelector(e.target);
                console.log('[Recorder] Drag started:', dragSourceSelector);
            }, true);

            document.addEventListener('drop', function(e) {
                if (dragSource && dragSourceSelector) {
                    const targetSelector = getBestSelector(e.target);
                    if (JSON.stringify(targetSelector) !== JSON.stringify(dragSourceSelector)) {
                        sendEvent({
                            action: 'drag_and_drop',
                            selector: dragSourceSelector,
                            value: targetSelector
                        });
                        console.log('[Recorder] Drag and drop recorded:', dragSourceSelector, '->', targetSelector);
                    }
                    dragSource = null;
                    dragSourceSelector = '';
                }
            }, true);

            document.addEventListener('dragend', function(e) {
                if (e.dataTransfer && e.dataTransfer.dropEffect === 'none') {
                    dragSource = null;
                    dragSourceSelector = '';
                }
            }, true);
        })();
        
        // 监听文件上传
        document.addEventListener('change', function(e) {
            const target = e.target;
            if (target.tagName.toLowerCase() === 'input' && target.type === 'file') {
                const files = target.files;
                if (files && files.length > 0) {
                    sendEvent({
                        action: 'upload',
                        selector: getBestSelector(target),
                        value: files[0].name,
                        fileCount: files.length
                    });
                }
            }
        }, true);
        
        // 监听弹窗
        const originalAlert = window.alert;
        const originalConfirm = window.confirm;
        const originalPrompt = window.prompt;
        
        window.alert = function(message) {
            sendEvent({
                action: 'alert_handle',
                selector: { type: 'css', css: 'window' },
                value: 'accept',
                alertType: 'alert',
                alertText: message
            });
            return originalAlert.apply(this, arguments);
        };
        
        window.confirm = function(message) {
            const result = originalConfirm.apply(this, arguments);
            sendEvent({
                action: 'alert_handle',
                selector: { type: 'css', css: 'window' },
                value: result ? 'accept' : 'dismiss',
                alertType: 'confirm',
                alertText: message
            });
            return result;
        };
        
        window.prompt = function(message, defaultValue) {
            const result = originalPrompt.apply(this, arguments);
            sendEvent({
                action: 'alert_handle',
                selector: { type: 'css', css: 'window' },
                value: result !== null ? 'accept' : 'dismiss',
                alertType: 'prompt',
                alertText: message,
                promptValue: result
            });
            return result;
        };
        
        console.log('[Recorder] Page info:', {
            url: window.location.href,
            title: document.title,
            viewport: { width: window.innerWidth, height: window.innerHeight }
        });
    })();
    """

class _RecorderState:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_recording = False
        self.is_paused = False


def _do_start(state, url, viewport):
    from playwright.sync_api import sync_playwright
    state.playwright = sync_playwright().start()
    state.browser = state.playwright.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    state.context = state.browser.new_context(
        viewport=viewport or {"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    state.page = state.context.new_page()

    def on_event(_source, payload):
        if state.is_paused:
            return
        emit({"type": "record_event", "data": payload})

    def on_assert_event(_source, payload):
        if state.is_paused:
            return
        emit({"type": "record_assert_event", "data": payload})

    state.page.expose_binding("onRecordEvent", on_event)
    state.page.expose_binding("onRecordAssertEvent", on_assert_event)
    state.page.add_init_script(RECORDING_SCRIPT)

    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    state.page.goto(url, wait_until="domcontentloaded", timeout=30000)
    state.page.evaluate(RECORDING_SCRIPT)

    state.is_recording = True
    emit({"type": "ready", "success": True})


def _do_stop(state):
    state.is_recording = False
    try:
        if state.page: state.page.close()
    except Exception: pass
    try:
        if state.context: state.context.close()
    except Exception: pass
    try:
        if state.browser: state.browser.close()
    except Exception: pass
    try:
        if state.playwright: state.playwright.stop()
    except Exception:
        logger.exception("playwright.stop 失败（可能有 driver 进程残留）")


def _do_run_step(state, step):
    from .runner_worker import _execute_single_step
    if not state.page:
        emit({"type": "step_run_done", "success": False, "code": "INTERNAL", "message": "未启动录制"})
        return
    try:
        _execute_single_step(state.page, step, lambda e: None)
        emit({"type": "step_run_done", "success": True})
    except Exception as e:
        emit({
            "type": "step_run_done", "success": False,
            "code": "INTERNAL", "message": str(e), "traceback": traceback.format_exc(),
        })


def main():
    _setup_io_logging()
    temp_dir = None
    state = _RecorderState()
    try:
        temp_dir = setup_temp_dir()
        emit({"type": "ready", "success": True, "phase": "temp_ready", "temp_dir": temp_dir})

        running = True
        while running:
            try:
                cmd = read_command()
            except json.JSONDecodeError as je:
                emit({"type": "error", "code": "INTERNAL", "message": f"无效 JSON: {je}"})
                continue
            except EOFError:
                break
            action = cmd.get("cmd")
            try:
                if action == "start":
                    _do_start(state, cmd.get("url", ""), cmd.get("viewport"))
                elif action == "pause":
                    state.is_paused = True
                    emit({"type": "paused"})
                elif action == "resume":
                    state.is_paused = False
                    emit({"type": "resumed"})
                elif action == "run_step":
                    _do_run_step(state, cmd.get("step") or {})
                elif action == "stop":
                    _do_stop(state)
                    emit({"type": "stopped", "success": True})
                    running = False
                else:
                    emit({"type": "error", "code": "INTERNAL", "message": f"未知命令: {action}"})
            except Exception as e:
                tb = traceback.format_exc()
                code = "LAUNCH_FAILED" if action == "start" else "INTERNAL"
                if "executable" in str(e).lower() and "doesn" in str(e).lower():
                    code = "BROWSER_NOT_INSTALLED"
                emit({"type": "error", "code": code, "message": str(e), "traceback": tb})
                if action == "start":
                    _do_stop(state)
    finally:
        _do_stop(state)
        if temp_dir:
            cleanup_temp_dir(temp_dir)


if __name__ == "__main__":
    main()
