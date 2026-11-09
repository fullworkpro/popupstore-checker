/**
 * 后台统一时间渲染：一律按北京时间（Asia/Shanghai）显示。
 *
 * 后端约定：时间戳一律输出带 +08:00 的 ISO 串；活动档期是纯日期，不在此处理。
 * 兼容策略：不带时区的 ISO 串按「已经是北京时间的字面值」解析，
 * 用于兼容历史落盘的任务状态文件（datetime.now() 写入，容器 TZ=Asia/Shanghai）。
 */
const TZ_RE = /(?:Z|[+-]\d{2}:?\d{2})$/
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

export function formatCN(value, fallback = '-') {
  if (!value) return fallback
  const s = String(value)
  if (DATE_ONLY_RE.test(s)) return s
  const iso = TZ_RE.test(s) ? s : `${s.replace(' ', 'T')}+08:00`
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
