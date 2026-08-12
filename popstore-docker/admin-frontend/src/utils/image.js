// 图片地址解析（管理端）
//  - 外链（http/https）：走后端同源代理 /api/v1/proxy-image，
//    绕过目标站防盗链(Referer)、混合内容、跨域等限制，让管理端能正常显示。
//  - 相对路径（/static/...）：同源 nginx 已代理到 backend，原样返回。
//  - data:/blob: 等：原样返回。
export function resolveImage(url) {
  if (!url) return ''
  const s = String(url).trim()
  if (!s) return ''
  // 已是代理地址，避免重复包装
  if (s.startsWith('/api/v1/proxy-image')) return s
  // 外链 -> 同源代理
  if (/^https?:\/\//i.test(s)) {
    return `/api/v1/proxy-image?url=${encodeURIComponent(s)}`
  }
  // 相对路径 / data: / 其它，原样
  return s
}
