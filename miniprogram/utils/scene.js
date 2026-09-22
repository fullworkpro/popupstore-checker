// 统一解析「小程序码 / 普通二维码 / 页面跳转」带进来的店铺 ID。
//
// 为什么要兜这么多写法 + 还要在首页做兜底：
// 实测存在「码里明明写了 path=pages/detail/detail，扫码却只进首页」的情况
// （path 未被微信执行，冷启动直接落在入口页）。所以不能只依赖 detail 页自己解析，
// 首页也要能把启动参数抠出来，再主动跳到对应详情页。
const ID_RE = /id=([0-9a-zA-Z-]{8,40})/
const RAW_RE = /^([0-9a-zA-Z-]{8,40})$/

function pick(s) {
  let str = '' + s
  try {
    str = decodeURIComponent(str)
  } catch (e) {
    // 解码失败就用原文，不让它把整条解析链路打断
  }
  let m = ID_RE.exec(str)
  if (m) return m[1]
  m = RAW_RE.exec(str.trim())
  if (m) return m[1]
  // 普通二维码里可能是完整 URL：https://xxx/...?id=xxx 或 /stores/xxx
  m = /\/stores\/([0-9a-zA-Z-]{8,40})/.exec(str)
  if (m) return m[1]
  return ''
}

// query 可以是 {id, scene, q} 这样的对象，也可以直接是一段裸字符串
function parseStoreId(query) {
  if (!query) return ''
  if (typeof query === 'string') return pick(query)
  const raws = [query.id, query.scene, query.q].filter(Boolean)
  for (const r of raws) {
    const hit = pick(r)
    if (hit) return hit
  }
  return ''
}

// 取本次「启动」的参数：扫码冷启动时，无论最终落在哪个页面都拿得到
function getLaunchQuery() {
  let query = {}
  try {
    const lo = wx.getLaunchOptionsSync()
    if (lo && lo.query) query = lo.query
  } catch (e) {
    // 低版本基础库没有该 API，走下面的 globalData 兜底
  }
  if (!Object.keys(query).length) {
    try {
      query = (getApp() && getApp().globalData.launchQuery) || {}
    } catch (e) {
      query = {}
    }
  }
  return query
}

module.exports = { parseStoreId, getLaunchQuery }
