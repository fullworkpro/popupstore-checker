const { getStores, resolveImage } = require('../../utils/api')

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
    stores: [],
    loading: false,
  },

  // 每次进入都刷新（从详情收藏/取消后会同步）
  onShow() {
    this.loadFavorites()
  },

  async loadFavorites() {
    const favIds = getFavIds()
    if (favIds.length === 0) {
      this.setData({ stores: [] })
      return
    }
    this.setData({ loading: true })
    try {
      // 拉取已发布快闪，按本地收藏 id 过滤
      const data = await getStores({ page: 1, page_size: 50, sort: 'newest' })
      const favSet = new Set(favIds)
      const stores = data.items
        .filter((s) => favSet.has(s.id))
        .map(normalize)
      this.setData({ stores })
    } catch (e) {
      console.error('收藏加载失败', e)
    } finally {
      this.setData({ loading: false })
    }
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` })
  },

  // 在收藏页直接取消收藏
  toggleFav(e) {
    const id = e.currentTarget.dataset.id
    let ids = getFavIds().filter((x) => x !== id)
    setFavIds(ids)
    this.loadFavorites()
  },
})

function normalize(s) {
  let cover = resolveImage(s.cover_image || '')
  if (!cover && s.images) {
    try {
      const arr = JSON.parse(s.images)
      if (arr && arr.length) cover = arr[0]
    } catch (e) { /* */ }
  }
  let cityList = []
  try {
    const cities = JSON.parse(s.cities || '[]')
    if (Array.isArray(cities) && cities.length) {
      cityList = cities.map((c) => (c && c.city) || '').filter(Boolean)
    }
  } catch (e) { /* */ }
  if (!cityList.length && s.city) cityList = [s.city]
  let tagList = []
  try { tagList = JSON.parse(s.tags || '[]').slice(0, 3) } catch (e) { /* */ }
  // 城市全部显示，不再截断；标签最多保留 3 个
  const displayTags = [...cityList, ...tagList]
  const dateText = formatRange(s.start_date, s.end_date)
  return Object.assign({}, s, { cover, cityText: cityList.join(' · '), tagList: displayTags, dateText })
}
