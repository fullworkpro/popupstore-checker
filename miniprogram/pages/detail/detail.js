const { getStoreDetail, resolveImage } = require('../../utils/api')

function parseISO(str) {
  if (!str) return null
  const s = '' + str
  const parts = s.split('T')
  let timePart = parts[1] || ''
  let cut = timePart.length
  const p = timePart.indexOf('+')
  const z = timePart.indexOf('Z')
  if (p >= 0) cut = Math.min(cut, p)
  if (z >= 0) cut = Math.min(cut, z)
  timePart = timePart.substring(0, cut)
  const d = parts[0].split('-')
  const t = timePart.split(':')
  const Y = parseInt(d[0], 10)
  const M = parseInt(d[1], 10) - 1
  const D = parseInt(d[2], 10)
  if (isNaN(Y) || isNaN(M) || isNaN(D)) return null
  return new Date(Y, M, D, parseInt(t[0], 10) || 0, parseInt(t[1], 10) || 0, 0)
}
function pad(n) { return n < 10 ? '0' + n : '' + n }
function fmtMD(dt) { return (dt.getMonth() + 1) + '/' + dt.getDate() }
function formatRange(startStr, endStr) {
  const s = parseISO(startStr)
  const e = parseISO(endStr)
  if (s && e) return fmtMD(s) + ' ~ ' + fmtMD(e)
  if (s) return fmtMD(s) + ' 起'
  if (e) return fmtMD(e) + ' 止'
  return '时间待定'
}

const FAV_KEY = 'popstore_favorites'

function getFavIds() {
  return wx.getStorageSync(FAV_KEY) || []
}
function setFavIds(ids) {
  wx.setStorageSync(FAV_KEY, ids)
}

Page({
  data: {
    store: {},
    images: [],
    cities: [],
    tagList: [],
    isFav: false,
    noId: false,
  },

  onLoad(options) {
    const id = this.pickStoreId(options)
    if (id) {
      const isFav = getFavIds().includes(id)
      this.setData({ isFav })
      this.fetchDetail(id)
    } else {
      // 扫码进入但没解析出店铺参数：显性提示（多半是线上版本太旧，没带 scene 解析）
      this.setData({ noId: true })
    }
  },

  // 从入参里尽量多地把店铺 ID 抠出来：
  // 1) 普通跳转 options.id
  // 2) 小程序码 scene=id=xxx（前缀匹配用，后端支持 8~35 位）
  // 3) scene 里是裸 id（没有 id= 前缀的旧码）
  // 4) 普通二维码 q=URL参数
  pickStoreId(options) {
    if (options.id) return options.id
    const raws = [options.scene, options.q].filter(Boolean)
    for (const raw of raws) {
      let s = String(raw)
      try { s = decodeURIComponent(s) } catch (e) { /* 保底用原文 */ }
      let m = /id=([0-9a-zA-Z-]{8,40})/.exec(s)
      if (m) return m[1]
      m = /^([0-9a-zA-Z-]{8,40})$/.exec(s.trim())
      if (m) return m[1]
    }
    return ''
  },

  goHome() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  async fetchDetail(id) {
    try {
      const store = await getStoreDetail(id)
      let images = []
      let cities = []
      let tagList = []

      try { images = (JSON.parse(store.images || '[]')).map(resolveImage) } catch { /* */ }
      try { cities = JSON.parse(store.cities || '[]') } catch { /* */ }
      try { tagList = JSON.parse(store.tags || '[]') } catch { /* */ }
      // 封面图同样解析（外链原样、相对路径拼主机）
      store.cover_image = resolveImage(store.cover_image)

      const RESV = { required: '需预约', advance: '前期需预约', no: '无需预约' }
      const reservationLabel = RESV[store.reservation] || '无需预约'

      // 预计算日期文本（不依赖 WXS，避免渲染崩溃）
      const dateText = formatRange(store.start_date, store.end_date)

      this.setData({ store, images, cities, tagList, reservationLabel, dateText })
    } catch (e) {
      console.error('详情加载失败', e)
      wx.showToast({ title: '加载失败', icon: 'error' })
    }
  },

  // 收藏 / 取消收藏（本地存储，仅本机生效）
  toggleFav() {
    const id = this.data.store.id
    if (!id) return
    let ids = getFavIds()
    if (ids.includes(id)) {
      ids = ids.filter((x) => x !== id)
      wx.showToast({ title: '已取消收藏', icon: 'none' })
    } else {
      ids = [id, ...ids]
      wx.showToast({ title: '已收藏', icon: 'success' })
    }
    setFavIds(ids)
    this.setData({ isFav: ids.includes(id) })
  },

  // 打开全屏看图：走微信原生预览，长图未放大即完整可见，放大后可上下/左右拖动看全
  openViewer(e) {
    const src = e.currentTarget.dataset.src
    if (!src) return
    let urls = (this.data.images || []).slice()
    if (!urls.length && this.data.store && this.data.store.cover_image) {
      urls = [this.data.store.cover_image]
    }
    if (urls.indexOf(src) < 0) urls.unshift(src)
    wx.previewImage({ current: src, urls })
  },

  onShareAppMessage() {
    return {
      title: this.data.store.title || '二次元快闪店',
      path: `/pages/detail/detail?id=${this.data.store.id}`,
    }
  },
})
