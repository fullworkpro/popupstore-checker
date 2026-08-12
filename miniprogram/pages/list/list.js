const { getStores, getTags, resolveImage } = require('../../utils/api')

Page({
  data: {
    stores: [],
    tags: [],
    keyword: '',
    activeTag: '',
    sort: 'newest',
    page: 1,
    pageSize: 20,
    loading: false,
    noMore: false,
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
      this.setData({ tags })
    } catch (e) { /* */ }
  },

  async fetchStores() {
    if (this.data.loading) return
    this.setData({ loading: true })

    try {
      const { page, pageSize, keyword, activeTag, sort } = this.data
      const params = { page, page_size: pageSize, sort }
      if (keyword) params.keyword = keyword
      if (activeTag) params.tag = activeTag

      const data = await getStores(params)
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

        return Object.assign({}, s, {
          cover,
          cityText: cityList.join(' · '),
          tagList: displayTags,
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
