// 复制到剪贴板（http 环境下 navigator.clipboard 不可用，回退 execCommand）
export async function copyText(text, tip = '已复制') {
  const s = String(text || '')
  if (!s) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(s)
    } else {
      const ta = document.createElement('textarea')
      ta.value = s
      ta.style.position = 'fixed'
      ta.style.top = '-1000px'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    if (tip) {
      const { ElMessage } = await import('element-plus')
      ElMessage.success(tip)
    }
    return true
  } catch (e) {
    const { ElMessage } = await import('element-plus')
    ElMessage.error('复制失败，请手动复制：' + s)
    return false
  }
}

// 小程序详情页路径（固定路由，公众号编辑器里插小程序卡片时要用）
export function mpPath(id) {
  return `pages/detail/detail?id=${id}`
}
