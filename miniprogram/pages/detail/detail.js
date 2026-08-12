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
    // 全屏看图
    viewerShow: false,
    viewerSrc: '',
    viewerScale: 1,
  },

  onLoad(options) {
    if (options.id) {
      const isFav = getFavIds().includes(options.id)
      this.setData({ isFav })
      this.fetchDetail(options.id)
    }
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

  // 打开全屏看图
  openViewer(e) {
    const src = e.currentTarget.dataset.src
    if (!src) return
    this.setData({ viewerShow: true, viewerSrc: src, viewerScale: 1 })
  },

  // 记录当前缩放比例（双指缩放时触发）
  onViewerScale(e) {
    this.setData({ viewerScale: e.detail.scale })
  },

  // 题图点击：默认比例下关闭全屏；已放大时不关闭（避免误触）
  onViewerImgTap(e) {
    if (this.data.viewerScale <= 1.05) {
      this.closeViewer()
    } else if (e && e.stopPropagation) {
      e.stopPropagation()
    }
  },

  closeViewer() {
    this.setData({ viewerShow: false, viewerSrc: '', viewerScale: 1 })
  },

  onShareAppMessage() {
    return {
      title: this.data.store.title || '二次元快闪店',
      path: `/pages/detail/detail?id=${this.data.store.id}`,
    }
  },
})
