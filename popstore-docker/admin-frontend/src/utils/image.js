// 图片地址解析（管理端）
//  - 外链（http/https）：默认【直连】目标站，不经过 NAS 代理，节省 NAS 上行带宽；
//    若目标站防盗链导致加载失败，由 SafeImage 自动回退到同源代理。
//  - 相对路径（/static/...）：同源 nginx 已代理到 backend，原样返回。
//  - data:/blob: 等：原样返回。
export function resolveImage(url) {
  if (!url) return ''
  const s = String(url).trim()
  if (!s) return ''
  // 已是代理地址，避免重复包装
  if (s.startsWith('/api/v1/proxy-image')) return s
  // 外链 -> 直连（节省带宽；失败由 SafeImage 回退代理）
  if (/^https?:\/\//i.test(s)) {
    return s
  }
  // 相对路径 / data: / 其它，原样
  return s
}

// 失败时回退用的同源代理地址（SafeImage 调用）
export function proxyImageUrl(url) {
  if (!url) return ''
  const s = String(url).trim()
  if (/^https?:\/\//i.test(s)) {
    return `/api/v1/proxy-image?url=${encodeURIComponent(s)}`
  }
  return s
}
