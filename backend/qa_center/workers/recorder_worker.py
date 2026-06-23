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
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
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
        if (window.__recorderInjected) return;
        window.__recorderInjected = true;
        console.log('[Recorder] v6 - Stable Selector Edition');

        // ============================================================
        // 1. 稳定 selector 算法
        // ============================================================
        const isStableId = function(id) {
            if (!id) return false;
            if (/^el-id-\d+-\d+$/.test(id)) return false;     // Element Plus 临时 id
            if (/^vue-\d+$/.test(id)) return false;            // vue dev
            if (/^[a-f0-9]{8,}$/i.test(id)) return false;      // hash
            return true;
        };
        const isStableClass = function(cls) {
            if (!cls || typeof cls !== 'string') return false;
            if (/^el-[a-z]/.test(cls)) return false;           // el-button / el-input__wrapper
            if (/^is-/.test(cls)) return false;                // is-active
            if (/^has-/.test(cls)) return false;               // has-error
            if (/^css-[a-z0-9]+$/.test(cls)) return false;      // css-modules
            if (/^data-v-/.test(cls)) return false;            // scoped style
            if (/^[a-z0-9]{8,}$/i.test(cls)) return false;     // hash
            return true;
        };
        const escapeAttr = function(v) {
            return String(v).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        };
        const trimText = function(t, max) {
            max = max || 30;
            t = (t || '').trim();
            if (t.length > max) t = t.substring(0, max);
            return t;
        };

        // 在 document 内统计 selector 命中数；自实现 :has-text 的本地校验
        const countMatches = function(sel) {
            const m = sel.match(/^([^]*?):has-text\("([^]*?)"\)$/);
            if (m) {
                let nodes;
                try { nodes = document.querySelectorAll(m[1]); } catch (_) { return -1; }
                let c = 0;
                for (let i = 0; i < nodes.length; i++) {
                    if (((nodes[i].textContent || '').trim()).indexOf(m[2]) >= 0) c++;
                }
                return c;
            }
            // playwright 专属语法（>> chain）无法本地校验
            if (sel.indexOf(' >> ') >= 0) return -1;
            let nodes;
            try { nodes = document.querySelectorAll(sel); } catch (_) { return -1; }
            return nodes.length;
        };

        // 可作路径前缀的 Element Plus 容器（块级布局节点）
        const STABLE_ELP_CONTAINER = /^(el-card|el-table|el-form-item|el-collapse-item|el-tabs__item|el-tab-pane|el-dialog|el-drawer|el-popover|el-step|el-tree-node|el-menu-item|el-dropdown-menu)$/;

        // 找一个"稳定"的祖先 selector 做路径前缀（最多向上 4 层）
        const getStableAncestorSel = function(el) {
            let cur = el.parentElement;
            for (let d = 0; d < 4 && cur; d++) {
                const t = (cur.tagName || '').toLowerCase();
                if (t && t !== 'body' && t !== 'html') {
                    if (cur.dataset && cur.dataset.testid) {
                        return '[data-testid="' + escapeAttr(cur.dataset.testid) + '"]';
                    }
                    const al = cur.getAttribute('aria-label');
                    if (al) return '[aria-label="' + escapeAttr(al) + '"]';
                    if (isStableId(cur.id)) return '#' + CSS.escape(cur.id);
                    if (cur.className && typeof cur.className === 'string') {
                        const parts = cur.className.split(/\s+/);
                        const stable = parts.filter(function(c) {
                            return c && isStableClass(c) && c.length > 3;
                        });
                        if (stable.length > 0) return '.' + stable[0];
                        // 容器类兜底：仅在能唯一时才返回，避免引入新歧义
                        const elContainer = parts.find(function(c) {
                            return STABLE_ELP_CONTAINER.test(c);
                        });
                        if (elContainer) {
                            if (countMatches('.' + elContainer) === 1) return '.' + elContainer;
                            const text = trimText(cur.textContent, 30);
                            if (text) {
                                const sel = '.' + elContainer + ':has-text("' + escapeAttr(text) + '")';
                                if (countMatches(sel) === 1) return sel;
                            }
                        }
                    }
                }
                cur = cur.parentElement;
            }
            return '';
        };

        // 校验 sel 在 document 唯一；不唯一时按文本/祖先路径退化，全失败返回空
        const ensureUnique = function(sel, el) {
            if (!sel) return '';
            const initial = countMatches(sel);
            if (initial === -1) return sel;   // 含 >> 等语法，相信 playwright
            if (initial === 1) return sel;
            if (initial === 0) return '';     // selector 在当前 dom 已不命中

            // A) 文本限定
            const text = trimText(el.textContent, 30);
            const hasText = sel.indexOf(':has-text(') >= 0;
            if (text && !hasText) {
                const cand = sel + ':has-text("' + escapeAttr(text) + '")';
                if (countMatches(cand) === 1) return cand;
            }

            // B) 稳定祖先路径前缀
            const anc = getStableAncestorSel(el);
            if (anc) {
                const cand1 = anc + ' ' + sel;
                if (countMatches(cand1) === 1) return cand1;
                if (text && !hasText) {
                    const cand2 = anc + ' ' + sel + ':has-text("' + escapeAttr(text) + '")';
                    if (countMatches(cand2) === 1) return cand2;
                }
            }

            // D) 位置索引兜底：用 Playwright 的 >> nth=N 链锁定原 sel 的第 N 个匹配
            //    回放时若 DOM 顺序变化会错位，但比完全录不上更可接受
            let nthNodes;
            try { nthNodes = document.querySelectorAll(sel); } catch (_) { nthNodes = null; }
            if (nthNodes && nthNodes.length > 1) {
                let idx = -1;
                for (let i = 0; i < nthNodes.length; i++) {
                    if (nthNodes[i] === el) { idx = i; break; }
                }
                if (idx >= 0) {
                    console.warn(
                        '[Recorder] selector 不唯一，使用 nth 索引兜底',
                        sel, '→', sel + ' >> nth=' + idx
                    );
                    return sel + ' >> nth=' + idx;
                }
            }

            // C) 全部失败 → 放弃（调用方跳过录制）
            return '';
        };

        // 返回 css 字符串；空字符串表示"找不到稳定 selector，跳过"
        const getCssSelector = function(el) {
            const tag = (el.tagName || '').toLowerCase();
            if (!tag || tag === 'html' || tag === 'body') return '';

            // 1. data-testid（最稳）
            if (el.dataset && el.dataset.testid) {
                return '[data-testid="' + escapeAttr(el.dataset.testid) + '"]';
            }
            // 2. aria-label（少数页面会重名 → 走 ensureUnique）
            const ariaLabel = el.getAttribute('aria-label');
            if (ariaLabel) {
                return ensureUnique('[aria-label="' + escapeAttr(ariaLabel) + '"]', el);
            }
            // 2.5 title（Element Plus 图标按钮普遍使用）
            const titleAttr = el.getAttribute('title');
            if (titleAttr) {
                return ensureUnique(tag + '[title="' + escapeAttr(titleAttr) + '"]', el);
            }
            // 3. 表单字段：placeholder / name / 关联 label
            if (tag === 'input' || tag === 'textarea' || tag === 'select') {
                if (el.placeholder) {
                    return ensureUnique('[placeholder="' + escapeAttr(el.placeholder) + '"]', el);
                }
                if (el.name) {
                    return '[name="' + escapeAttr(el.name) + '"]';
                }
                if (el.type === 'file') {
                    return 'input[type="file"]' + (el.name ? '[name="' + escapeAttr(el.name) + '"]' : '');
                }
                // 关联 <label for="id">
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) {
                        const t = trimText(lbl.textContent, 20);
                        if (t) return 'label:has-text("' + escapeAttr(t) + '") >> ' + tag;
                    }
                }
                // el-form-item 容器
                const formItem = el.closest('.el-form-item');
                if (formItem) {
                    const lbl = formItem.querySelector('.el-form-item__label');
                    if (lbl) {
                        const t = trimText(lbl.textContent, 20);
                        if (t) return '.el-form-item:has(.el-form-item__label:has-text("' + escapeAttr(t) + '")) ' + tag;
                    }
                }
            }
            // 4. 稳定 id
            if (isStableId(el.id)) {
                return '#' + CSS.escape(el.id);
            }
            // 5. button / a / heading 用文本（重名走 ensureUnique 加祖先路径）
            if (tag === 'button' || tag === 'a') {
                const t = trimText(el.textContent, 20);
                if (t) return ensureUnique(tag + ':has-text("' + escapeAttr(t) + '")', el);
            }
            if (/^h[1-6]$/.test(tag)) {
                const t = trimText(el.textContent, 30);
                if (t) return ensureUnique(tag + ':has-text("' + escapeAttr(t) + '")', el);
            }
            // 5.5 Element Plus 控件本体：el-* 类不是 hash，
            // 配合 form-item label / 自身文本能稳定锁定，是 isStableClass 一刀切的白名单
            const ELP_ANCHOR_CLASSES = [
                'el-checkbox', 'el-radio', 'el-switch',
                'el-select__wrapper', 'el-select-v2__wrapper', 'el-select',
                'el-button', 'el-input-number', 'el-rate', 'el-slider',
                'el-date-editor', 'el-time-picker', 'el-color-picker',
                'el-tag', 'el-link',
            ];
            if (el.classList) {
                for (let i = 0; i < ELP_ANCHOR_CLASSES.length; i++) {
                    const cls = ELP_ANCHOR_CLASSES[i];
                    if (!el.classList.contains(cls)) continue;
                    // a) form-item label 锁定
                    const formItem = el.closest('.el-form-item');
                    if (formItem) {
                        const lbl = formItem.querySelector('.el-form-item__label');
                        const lt = lbl && trimText(lbl.textContent, 20);
                        if (lt) {
                            const fSel = '.el-form-item:has(.el-form-item__label:has-text("'
                                         + escapeAttr(lt) + '")) .' + cls;
                            if (countMatches(fSel) === 1) return fSel;
                        }
                    }
                    // b) 自身文本锁定
                    const t2 = trimText(el.textContent, 20);
                    if (t2) {
                        const cand = '.' + cls + ':has-text("' + escapeAttr(t2) + '")';
                        if (countMatches(cand) === 1) return cand;
                    }
                    // c) 走 ensureUnique（会再尝试加祖先路径）
                    const u = ensureUnique('.' + cls, el);
                    if (u) return u;
                    break;  // 已尝试匹配的锚点类失败，无需再试其他锚点
                }
            }
            // 6. 稳定业务 class（最易撞车，强制走 ensureUnique）
            if (el.className && typeof el.className === 'string') {
                const stable = el.className.split(/\s+/).filter(function(c) {
                    return c && isStableClass(c) && c.length > 3;
                });
                if (stable.length > 0) {
                    return ensureUnique('.' + stable[0], el);
                }
            }
            // 7. 走到这里说明既无文本/属性/稳定 class，全局 tag 兜底毫无指向性 → 放弃
            return '';
        };

        // ============================================================
        // 2. 工具函数
        // ============================================================
        // 找最近的可交互父元素（处理点击 icon 嵌套场景）
        const hasIconClass = function(node) {
            if (!node || !node.classList) return false;
            for (let i = 0; i < node.classList.length; i++) {
                if (node.classList[i].indexOf('icon') >= 0) return true;
            }
            return false;
        };
        const resolveInteractive = function(el) {
            const inlineTags = ['span', 'i', 'em', 'strong', 'b', 'svg', 'path',
                                'circle', 'rect', 'g', 'use', 'img'];
            let cur = el;
            for (let depth = 0; depth < 6 && cur; depth++) {
                const tag = (cur.tagName || '').toLowerCase();
                // 仅检查当前节点本身是否是 inline / icon —— 不能再用 closest
                // 上溯到祖先（否则远端有任何 .icon-* 都会让按钮被误跳过）
                if (!inlineTags.includes(tag) &&
                    tag !== 'font-awesome-icon' &&
                    !hasIconClass(cur)) {
                    return cur;
                }
                cur = cur.parentElement;
            }
            return el;
        };
        // 用户点的是表单输入框容器（el-input 内部 wrapper / .el-textarea__inner 等）
        // 此时 fill 会自动触发，不要把 click 也录了
        const isInsideFormInput = function(el) {
            let cur = el;
            for (let i = 0; i < 5 && cur; i++) {
                const tag = (cur.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
                if (cur.isContentEditable) return true;
                if (cur.classList && (
                    cur.classList.contains('el-input__wrapper') ||
                    cur.classList.contains('el-textarea__inner')
                )) return true;
                cur = cur.parentElement;
            }
            return false;
        };
        // 选中的伪控件（checkbox/radio/switch）：内部有 input 但需要 click wrapper 切换
        const PSEUDO_TOGGLE_SELECTOR = '.el-checkbox, .el-radio, .el-switch';
        const findPseudoToggle = function(el) {
            return el && el.closest ? el.closest(PSEUDO_TOGGLE_SELECTOR) : null;
        };
        const findSelectWrapper = function(el) {
            return el && el.closest
                ? el.closest('.el-select__wrapper, .el-select-v2__wrapper, .el-select, .el-select-v2')
                : null;
        };
        const isToolbar = function(el) {
            return el.closest && (
                el.closest('#recorder-assert-toolbar') ||
                el.closest('#recorder-overlay')
            );
        };

        // ============================================================
        // 3. 事件发送 + 去重/防抖
        // ============================================================
        const dedupeMap = new Map();   // key -> ts
        const fillDebounce = new Map(); // selectorKey -> {selector, value, timer, target}

        const sendEvent = function(data) {
            if (!data.selector) {
                console.warn(
                    '[Recorder] 跳过录制：当前元素缺少稳定 selector（建议加 data-testid / aria-label / title）',
                    data.action
                );
                return;
            }
            const key = data.action + '|' + data.selector;
            const now = Date.now();
            const last = dedupeMap.get(key) || 0;
            if (now - last < 200) {
                console.log('[Recorder] dedup', data.action, data.selector);
                return;
            }
            dedupeMap.set(key, now);
            console.log('[Recorder] send', data.action, data.selector);
            window.onRecordEvent(data);
        };
        const commitFill = function(selKey) {
            const ent = fillDebounce.get(selKey);
            if (!ent) return;
            fillDebounce.delete(selKey);
            sendEvent({ action: 'fill', selector: ent.selector, value: ent.value });
        };
        // 表单值变化时调用：同 selector 多次调用会合并，最终值在 400ms 无更新后提交
        const scheduleFill = function(target, value) {
            const sel = getCssSelector(target);
            if (!sel) return;
            const key = 'fill|' + sel;
            let ent = fillDebounce.get(key);
            if (!ent) { ent = {}; fillDebounce.set(key, ent); }
            ent.selector = sel;
            ent.value = value;
            if (ent.timer) clearTimeout(ent.timer);
            ent.timer = setTimeout(function() { commitFill(key); }, 400);
        };
        // 离开表单字段时立即提交（不等 400ms）
        const flushFill = function(target) {
            const sel = getCssSelector(target);
            if (!sel) return;
            const key = 'fill|' + sel;
            if (fillDebounce.has(key)) commitFill(key);
        };

        // ============================================================
        // 4. 断言模式 UI
        // ============================================================
        let isAssertMode = false;
        // 最近一次按下的 el-select wrapper：dropdown__item 是 teleport 到 body 的，
        // 失去与 wrapper 的 DOM 父子关系，因此用 mousedown 捕获记下来源 wrapper。
        let lastSelectWrapper = null;
        const enterAssertMode = function() {
            isAssertMode = true;
            document.body.classList.add('recorder-assert-cursor');
            const btn = document.getElementById('recorder-assert-btn');
            if (btn) {
                btn.classList.add('active');
                btn.innerHTML = '<span>🎯</span><span>点击目标元素（取消按 Esc）</span>';
            }
        };
        const exitAssertMode = function() {
            isAssertMode = false;
            document.body.classList.remove('recorder-assert-cursor');
            const btn = document.getElementById('recorder-assert-btn');
            if (btn) {
                btn.classList.remove('active');
                btn.innerHTML = '<span>🎯</span><span>验证元素 (Assert)</span>';
            }
        };
        const createAssertToolbar = function() {
            if (document.getElementById('recorder-assert-toolbar')) return;
            const toolbar = document.createElement('div');
            toolbar.id = 'recorder-assert-toolbar';
            toolbar.innerHTML = '<style>' +
                '#recorder-assert-toolbar {position:fixed;bottom:20px;right:20px;z-index:2147483647;font-family:-apple-system,BlinkMacSystemFont,sans-serif;}' +
                '#recorder-assert-toolbar .assert-btn {background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;padding:12px 20px;border-radius:25px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 4px 15px rgba(102,126,234,.4);}' +
                '#recorder-assert-toolbar .assert-btn.active {background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);}' +
                'body.recorder-assert-cursor, body.recorder-assert-cursor * {cursor:crosshair !important;}' +
                '</style>' +
                '<button class="assert-btn" id="recorder-assert-btn"><span>🎯</span><span>验证元素 (Assert)</span></button>';
            document.body.appendChild(toolbar);
            document.getElementById('recorder-assert-btn').addEventListener('click', function(e) {
                e.stopPropagation();
                if (isAssertMode) exitAssertMode(); else enterAssertMode();
            });
        };
        const handleAssertEvent = function(target) {
            const sel = getCssSelector(target);
            if (!sel) return;
            const text = trimText(target.textContent, 50);
            let action = 'assert_visible';
            let value = '';
            let attribute = '';
            if (text && text.length > 0 && text.length < 100) {
                action = 'assert_contains_text';
                value = text;
            }
            exitAssertMode();
            window.onRecordAssertEvent({
                action: action, selector: sel, value: value, attribute: attribute,
            });
        };

        // ============================================================
        // 5. 事件监听
        // ============================================================
        // mousedown（capture）：记录用户按下的 el-select wrapper，供 dropdown__item click 关联
        document.addEventListener('mousedown', function(e) {
            if (isToolbar(e.target)) return;
            const w = findSelectWrapper(e.target);
            if (w) lastSelectWrapper = w;
        }, true);

        // click：录 button/link/heading 等真实点击；过滤 input wrapper
        document.addEventListener('click', function(e) {
            if (isToolbar(e.target)) return;

            // 诊断：每次 click 打印 target 与 composedPath（前 5 层）
            try {
                const path = (e.composedPath ? e.composedPath() : []).slice(0, 5).map(function(n) {
                    if (!n || !n.tagName) return '?';
                    const cls = (n.className || '').toString().split(/\s+/)[0] || '';
                    return n.tagName + (cls ? '.' + cls : '');
                }).join(' < ');
                console.log('[Recorder][click] target=', e.target.tagName,
                            (e.target.className || '').toString(),
                            'path=', path);
            } catch (_) {}

            if (isAssertMode) {
                e.preventDefault();
                e.stopPropagation();
                handleAssertEvent(resolveInteractive(e.target));
                return;
            }

            // 5a. el-select 下拉项：teleport 到 body，需借助 lastSelectWrapper 还原 selector
            const dropItem = e.target.closest && e.target.closest('.el-select-dropdown__item');
            if (dropItem) {
                const wrapper = lastSelectWrapper;
                lastSelectWrapper = null;
                if (!wrapper) return;
                const sel = getCssSelector(wrapper);
                if (!sel) return;
                const value = trimText(dropItem.textContent, 100);
                sendEvent({ action: 'select', selector: sel, value: value });
                return;
            }

            // 5b. el-checkbox / el-radio / el-switch：内部有 input，但实际靠 click wrapper 切换
            const pseudo = findPseudoToggle(e.target);
            if (pseudo) {
                const sel = getCssSelector(pseudo);
                if (!sel) return;
                sendEvent({ action: 'click', selector: sel, value: '' });
                return;
            }

            // 5b.5 用户点击 el-select wrapper（含 v2）：按 popper 可见性区分意图
            //   - popper 关闭态 → 这次 click 是"展开"，吞掉，等 dropdown__item 选中发 select；
            //   - popper 展开态 → 这次 click 是"关闭"（多选后用户主动收），录为 click。
            //   capture 阶段先于 Vue 处理，此处看到的状态 = 本次 click 之前的状态。
            const selectWrapper = findSelectWrapper(e.target);
            if (selectWrapper) {
                let popperOpen = false;
                try {
                    const poppers = document.querySelectorAll('.el-select-dropdown');
                    for (let i = 0; i < poppers.length; i++) {
                        // offsetParent 为 null 即 display:none，更贴近"用户感知的打开"
                        if (poppers[i].offsetParent !== null) { popperOpen = true; break; }
                    }
                } catch (_) {}

                if (!popperOpen) {
                    console.log('[Recorder] 跳过打开 el-select 的 wrapper click');
                    return;
                }
                const sel = getCssSelector(selectWrapper);
                if (!sel) return;
                console.log('[Recorder] 录制关闭 el-select wrapper click');
                sendEvent({ action: 'click', selector: sel, value: '' });
                return;
            }

            const target = resolveInteractive(e.target);
            if (isInsideFormInput(target)) {
                // 用户点击 input/textarea 容器：fill 会自动触发，不录 click
                return;
            }
            const sel = getCssSelector(target);
            if (!sel) return;
            sendEvent({ action: 'click', selector: sel, value: '' });
        }, true);

        // change：录 fill/select/upload
        document.addEventListener('change', function(e) {
            const t = e.target;
            const tag = (t.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea') {
                if (t.type === 'file') {
                    const sel = getCssSelector(t);
                    if (!sel) return;
                    const files = t.files || [];
                    sendEvent({
                        action: 'upload',
                        selector: sel,
                        value: files[0] ? files[0].name : '',
                    });
                    return;
                }
                scheduleFill(t, t.value || '');
            } else if (tag === 'select') {
                const sel = getCssSelector(t);
                if (!sel) return;
                sendEvent({ action: 'select', selector: sel, value: t.value });
            }
        }, true);

        // blur：立即提交 pending fill（不等 400ms）
        document.addEventListener('blur', function(e) {
            const t = e.target;
            const tag = (t.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea') {
                flushFill(t);
            }
        }, true);

        // keydown：只录 Enter（提交）和 Tab（跳转）
        document.addEventListener('keydown', function(e) {
            if (isToolbar(e.target)) return;
            if (e.key === 'Enter' || e.key === 'Tab') {
                // Enter 提交时：先 flush 当前 input 的 fill
                if (e.key === 'Enter') {
                    const t = e.target;
                    const tag = (t.tagName || '').toLowerCase();
                    if (tag === 'input' || tag === 'textarea') {
                        flushFill(t);
                    }
                }
                const sel = getCssSelector(e.target);
                if (!sel) return;
                sendEvent({ action: 'keydown', selector: sel, value: e.key });
            }
        }, true);

        // Esc 退出断言模式
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isAssertMode) {
                exitAssertMode();
            }
        }, true);

        createAssertToolbar();
        console.log('[Recorder] Ready');
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
