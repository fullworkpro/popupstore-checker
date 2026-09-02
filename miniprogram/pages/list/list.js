const { getStores, getTags, resolveImage } = require('../../utils/api')

// 快闪类型：与后台 models/store.py 的 STORE_TYPES 保持一致
const STORE_TYPES = [
  { value: 'popup', label: '联名快闪' },
  { value: 'exhibition', label: '特展' },
  { value: 'restaurant', label: '联名餐厅' },
]
const DEFAULT_STORE_TYPE = 'popup'

Page({
  data: {
    stores: [],
    tags: [],
    keyword: '',
    activeTag: '',
    // 快闪类型：空 = 全部；具体值走后端 store_type 筛选
    typeOptions: STORE_TYPES,
    activeType: '',
    sort: 'newest',
    page: 1,
    pageSize: 20,
    loading: false,
    noMore: false,

    // 标签栏：收起态只显示一行，超出一行才显示「展开」按钮
    tagExpanded: false,
    showTagToggle: false,
  },

  onLoad() {
    this.fetchStores()
    this.fetchTags()
  },

  onPullDownRefresh() {
    this.setData({ page: 1, stores: [], noMore: false })
    this.fetchStores().then(() => wx.stopPullDownRefresh())
  },

  onReachBottom() {
    if (!this.data.noMore && !this.data.loading) {
      this.fetchStores()
    }
  },

  async fetchTags() {
    try {
      const tags = await getTags()
      // 渲染完成后再测量，否则拿不到真实高度
      this.setData({ tags }, () => this._measureTags())
    } catch (e) { /* */ }
  },

  // 判断标签是否超出一行：量出 .tag-inner 的实际高度，与「单行高度」比较。
  // 单行标签高 52rpx，需按屏幕宽度把 rpx 折算成 px（750rpx = 屏宽）。
  _measureTags() {
    if (!this.data.tags || !this.data.tags.length) {
      this.setData({ showTagToggle: false })
      return
    }
    let windowWidth = 375
    try {
      const info = (wx.getWindowInfo && wx.getWindowInfo()) ||
        (wx.getSystemInfoSync && wx.getSystemInfoSync()) || {}
      windowWidth = info.windowWidth || 375
    } catch (e) { /* 取不到就用默认 375 */ }

    const oneRowPx = (52 * windowWidth) / 750

    wx.createSelectorQuery()
      .in(this)
      .select('.tag-inner')
      .boundingClientRect((rect) => {
        const h = (rect && rect.height) || 0
        if (!h) return
        // 超过 1.5 行才认为「放不下」，避免个别机型四舍五入导致误判
        this.setData({ showTagToggle: h > oneRowPx * 1.5 })
      })
      .exec()
  },

  toggleTags() {
    this.setData({ tagExpanded: !this.data.tagExpanded })
  },

  async fetchStores() {
    // 请求序号：每次发起都 +1，响应回来时若已不是最新序号则丢弃，避免竞态导致错乱。
    // 这样用户主动点击筛选时，即使上一次请求（首屏/上拉）还在进行，也能立刻打断并拿到正确结果。
    if (this._reqSeq == null) this._reqSeq = 0
    const seq = ++this._reqSeq

    // 注意：这里不再用 this.data.loading 提前 return。
    // loading 闸门原本只用于防止「上拉加载更多」重复刷，但它会顺带吞掉用户主动点击
    // 筛选的请求（点击后 activeType 已更新、视图高亮变化，却因 loading 为 true 而不发请求）。
    // 上拉加载的拦截改由 onReachBottom 自身判断 !loading 负责。
    this.setData({ loading: true })

    const { page, pageSize, keyword, activeTag, activeType, sort } = this.data
    const params = { page, page_size: pageSize, sort }
    if (keyword) params.keyword = keyword
    if (activeTag) params.tag = activeTag
    if (activeType) params.store_type = activeType

    console.log('[fetchStores] 发起请求', JSON.stringify(params), 'seq=', seq)

    try {
      const data = await getStores(params)
      if (seq !== this._reqSeq) {
        console.log('[fetchStores] 丢弃过期响应 seq=', seq, '(已有更新的请求)')
        return
      }
      const raw = page === 1 ? data.items : [...this.data.stores, ...data.items]
      const stores = raw.map((s) => {
        let cover = resolveImage(s.cover_image || '')
        if (!cover && s.images) {
          try {
            const arr = JSON.parse(s.images)
            if (arr && arr.length) cover = arr[0]
          } catch (e) { /* */ }
        }

        // 多城市：取出所有城市名
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

        // 后端老数据可能没有 store_type，回退默认类型，保证卡片上不会出现空白徽章
        const storeType = s.store_type || DEFAULT_STORE_TYPE
        const typeLabel = (STORE_TYPES.filter((t) => t.value === storeType)[0] || STORE_TYPES[0]).label

        return Object.assign({}, s, {
          cover,
          cityText: cityList.join(' · '),
          tagList: displayTags,
          storeType,
          typeLabel,
        })
      })
      this.setData({
        stores,
        page: page + 1,
        noMore: data.items.length < pageSize,
      })
    } catch (e) {
      console.error('列表加载失败', e)
    } finally {
      this.setData({ loading: false })
    }
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value })
  },

  onSearch() {
    this.setData({ page: 1, stores: [], noMore: false })
    this.fetchStores()
  },

  filterTag(e) {
    const tag = e.currentTarget.dataset.tag
    this.setData({ activeTag: tag, page: 1, stores: [], noMore: false })
    this.fetchStores()
  },

  // 类型条容器的兜底点击：仅做「点击事件被分发到了」的自检
  // 出现「点了标签没反应」时，看 console 有没有这一行就知道是事件没触发（缓存）
  // 还是触发了但 setData 没生效（真 bug）
  onTypeBarTap(e) {
    try {
      console.log('[type-bar] click received, target dataset =', e && e.target && e.target.dataset)
    } catch (err) { /* */ }
  },

  filterType(e) {
    const type = e.currentTarget.dataset.type || ''
    if (this.data.activeType === type) return
    this.setData({ activeType: type, page: 1, stores: [], noMore: false })
    this.fetchStores()
  },

  changeSort(e) {
    const sort = e.currentTarget.dataset.sort
    this.setData({ sort, page: 1, stores: [], noMore: false })
    this.fetchStores()
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` })
  },
})
