/**
 * 安全渲染工具
 * 提供 XSS 防护和文本转义功能
 */

/**
 * HTML 特殊字符转义表
 */
const HTML_ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
  '/': '&#x2F;',
};

/**
 * 转义 HTML 特殊字符
 * @param text 输入文本
 * @returns 转义后的纯文本
 */
export function escapeHtml(text: string): string {
  if (!text) return '';
  return text.replace(/[&<>"'/]/g, (char) => HTML_ESCAPE_MAP[char] || char);
}

/**
 * 安全渲染文本（不保留任何 HTML 标签）
 * 用于用户输入的内容展示，防止 XSS 攻击
 * @param text 输入文本
 * @returns 转义后的安全文本
 */
export function sanitizeText(text: string): string {
  if (!text) return '';
  return escapeHtml(text);
}

/**
 * 高亮搜索关键词（安全版本）
 * 将匹配到的关键词用 <mark> 标签包裹
 * 输入文本会被转义，关键词也会被转义后用于匹配
 * @param text 原文本
 * @param keyword 搜索关键词
 * @returns 带高亮的 HTML 字符串
 */
export function highlightText(text: string, keyword: string): string {
  if (!text) return '';

  // 转义原文本
  const escapedText = escapeHtml(text);

  if (!keyword) return escapedText;

  // 对关键词进行转义，防止 XSS
  const escapedKeyword = escapeHtml(keyword);

  // 转义关键词中的特殊正则字符（转义后再转正则）
  const escapedKeywordForRegex = escapedKeyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // 替换匹配项
  const regex = new RegExp(`(${escapedKeywordForRegex})`, 'gi');
  return escapedText.replace(regex, '<mark style="background-color: #ffd700; font-weight: bold;">$1</mark>');
}

/**
 * 截断文本并添加省略号
 * @param text 原文本
 * @param maxLength 最大长度
 * @returns 截断后的文本
 */
export function truncateText(text: string, maxLength: number = 100): string {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}

/**
 * 去除文本中的空白字符
 * @param text 原文本
 * @returns 去除空白后的文本
 */
export function trimText(text: string): string {
  if (!text) return '';
  return text.trim().replace(/\s+/g, ' ');
}