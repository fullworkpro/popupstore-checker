const { getStores, resolveImage } = require('../../utils/api')

// 为每个快闪店分配一个颜色，日历色条与列表左侧色条共用，便于对应
const PALETTE = [
  '#6C5CE7', '#00B894', '#FD79A8', '#E17055',
  '#0984E3', '#FDCB6E', '#A29BFE', '#00CEC9',
  '#D63031', '#74B9FF', '#55EFC4', '#F79F1F',
]

// 快闪类型：与后台 models/store.py 的 STORE_TYPES 保持一致
const STORE_TYPES = [
  { value: 'popup', label: '联名快闪' },
  { value: 'exhibition', label: '特展' },
  { value: 'restaurant', label: '联名餐厅' },
]
const DEFAULT_STORE_TYPE = 'popup'
// 默认城市：无论数据里有没有，都固定排在选项首位
const DEFAULT_CITY = '广州'

// 记住用户最后一次选择的城市/类型，下次打开小程序自动恢复
const CITY_STORAGE_KEY = 'popstore_last_city'
const TYPE_STORAGE_KEY = 'popstore_last_type'

const FUTURE = new Date(2099, 0, 1)

// 手动解析 ISO 日期串，只取日期部分
function parseISO(str) {
  if (!str) return null
  const s = '' + str
  const parts = s.split('T')
  const datePart = parts[0]
  const d = datePart.split('-')
  const Y = parseInt(d[0], 10)
  const M = parseInt(d[1], 10) - 1
  const D = parseInt(d[2], 10)
  if (isNaN(Y) || isNaN(M) || isNaN(D)) return null
  return dateOnly(new Date(Y, M, D, 0, 0, 0))
}

function dateOnly(dt) {
  if (!dt) return dt
  return new Date(dt.getFullYear(), dt.getMonth(), dt.getDate(), 0, 0, 0)
}

function pad(n) { return n < 10 ? '0' + n : '' + n }

function fmtMD(dt) {
  return (dt.getMonth() + 1) + '/' + dt.getDate()
}

function dateStr(dt) {
  return dt.getFullYear() + '-' + pad(dt.getMonth() + 1) + '-' + pad(dt.getDate())
}

// 预处理：封面、城市文本、日期范围文本、配色
function normalizeStore(s, idx) {
  let cover = resolveImage(s.cover_image || '')
  if (!cover && s.images) {
    try {
      const arr = JSON.parse(s.images)
      if (arr && arr.length) cover = arr[0]
    } catch (e) { /* */ }
  }
  let cityList = []
  try {
    const cs = JSON.parse(s.cities || '[]')
    if (Array.isArray(cs) && cs.length) {
      cityList = cs.map((c) => (c && c.city) || '').filter(Boolean)
    }
  } catch (e) { /* */ }
  if (!cityList.length && s.city) cityList = [s.city]
  const cityText = cityList.join(' · ')

  const start = parseISO(s.start_date)
  const endRaw = parseISO(s.end_date)
  const end = endRaw || FUTURE
  let dateText = '时间待定'
  if (start && endRaw) dateText = fmtMD(start) + ' - ' + fmtMD(endRaw)
  else if (start) dateText = fmtMD(start) + ' 起'
  else if (endRaw) dateText = fmtMD(endRaw) + ' 止'

  return Object.assign({}, s, {
    cover,
    cityText,
    cityList,
    // 后端老数据可能没有 store_type，回退默认类型，保证筛选不漏数据
    storeType: s.store_type || DEFAULT_STORE_TYPE,
    typeLabel: (STORE_TYPES.filter((t) => t.value === (s.store_type || DEFAULT_STORE_TYPE))[0] || STORE_TYPES[0]).label,
    start,
    end,
    dateText,
    color: PALETTE[idx % PALETTE.length],
  })
}

Page({
  data: {
    viewYear: 2026,
    viewMonth: 8,
    weeks: [],
    monthLabel: '',
    todayStr: '',
    allStores: [],
    filteredStores: [],
    monthStores: [],
    visibleStores: [],
    selectedDate: '',
    selectedColor: '',
    canPrev: true,
    canNext: true,
    loading: false,

    // 首页筛选：城市 + 快闪类型（单选下拉，默认 广州 / 联名快闪）
    cityOptions: [DEFAULT_CITY],
    cityIndex: 0,
    typeOptions: STORE_TYPES,
    typeIndex: 0,
    filterLabel: DEFAULT_CITY + ' · ' + STORE_TYPES[0].label,
    emptyText: '',
  },

  onLoad() {
    const now = dateOnly(new Date())
    // 基准月：当前真实年月，用于限制可翻动范围（上一个月 ~ 下两个月）
    this._baseY = now.getFullYear()
    this._baseM = now.getMonth() + 1

    // 恢复上次选择的城市/类型：城市选项要等接口回来才建得出来，
    // 所以先记在 _preferredCity 里，由 _rebuildCityOptions 负责落地。
    this._preferredCity = this._readStorage(CITY_STORAGE_KEY) || DEFAULT_CITY
    const savedType = this._readStorage(TYPE_STORAGE_KEY)
    const savedTypeIdx = STORE_TYPES.map((t) => t.value).indexOf(savedType)
    const typeIndex = savedTypeIdx >= 0 ? savedTypeIdx : 0

    this.setData({
      viewYear: now.getFullYear(),
      viewMonth: now.getMonth() + 1,
      todayStr: dateStr(now),
      typeIndex,
      // 首帧先按恢复的城市/类型渲染文案，接口回来后由 _applyFilters 校正
      filterLabel: this._preferredCity + ' · ' + STORE_TYPES[typeIndex].label,
    }, () => {
      // 先渲染空月历框架，避免等待接口时页面空白
      this.buildCalendar()
      this.loadStores()
    })
  },

  // Storage 读取兜底：小程序存储不可用（如隐私模式/超配额）时不影响主流程
  _readStorage(key) {
    try {
      return wx.getStorageSync(key) || ''
    } catch (e) {
      return ''
    }
  },

  _writeStorage(key, value) {
    try {
      wx.setStorageSync(key, value)
    } catch (e) { /* 存不了就算了，不影响本次使用 */ }
  },

  // 当前视图月相对基准月的差值（月），用于翻页边界判断
  _monthOffset() {
    return (this.data.viewYear - this._baseY) * 12 + (this.data.viewMonth - this._baseM)
  },

  onShow() {
    // 从其他页面或 tab 返回时刷新数据
    this.loadStores()
  },

  onPullDownRefresh() {
    this.loadStores().then(() => {}, () => {}).finally(() => wx.stopPullDownRefresh())
  },

  // 一次性拉取全部已发布快闪（数据量小，客户端按月份/日期过滤）
  async loadStores() {
    if (this.data.loading) return
    this.setData({ loading: true })
    try {
      const data = await getStores({ page: 1, page_size: 200 })
      const all = (data.items || []).map(normalizeStore)
      // 刷新后重建城市选项（数据里的城市可能变了），再按当前筛选条件重算
      this._rebuildCityOptions(all)
      this.setData({ allStores: all }, () => {
        this._applyFilters()
        this.buildCalendar()
      })
    } catch (e) {
      console.error('加载失败', e)
      // 即使接口失败也保持月历框架渲染，并提示用户
      this.buildCalendar()
      wx.showToast({ title: '数据加载失败', icon: 'none' })
    }
  },

  // 城市选项：默认城市固定首位，其余按数据中出现的城市排序去重
  _rebuildCityOptions(all) {
    const set = {}
    ;(all || []).forEach((s) => {
      ;(s.cityList || []).forEach((c) => {
        if (c) set[c] = true
      })
    })
    const others = Object.keys(set).filter((c) => c !== DEFAULT_CITY).sort()
    const options = [DEFAULT_CITY].concat(others)

    // 选中优先级：用户最后选过的城市 > 当前选中的城市 > 默认城市
    // （默认城市恒为 options[0]，所以兜底 idx 一定是 0）
    const cur = this._preferredCity || this.data.cityOptions[this.data.cityIndex]
    let idx = options.indexOf(cur)
    if (idx < 0) idx = 0
    this.setData({ cityOptions: options, cityIndex: idx })
  },

  // 按「城市 + 快闪类型」过滤，结果供月历与列表使用
  _applyFilters() {
    const { allStores, cityOptions, cityIndex, typeOptions, typeIndex } = this.data
    const city = cityOptions[cityIndex]
    const type = (typeOptions[typeIndex] || {}).value || DEFAULT_STORE_TYPE

    const filtered = (allStores || []).filter((s) => {
      if ((s.storeType || DEFAULT_STORE_TYPE) !== type) return false
      if (!city) return true
      return (s.cityList || []).indexOf(city) >= 0
    })

    this.setData({
      filteredStores: filtered,
      filterLabel: city + ' · ' + ((typeOptions[typeIndex] || {}).label || ''),
    })
  },

  onCityChange(e) {
    const idx = Number(e.detail.value) || 0
    const city = this.data.cityOptions[idx]
    // 记住选择，下次打开小程序自动落在同一个城市
    this._preferredCity = city
    this._writeStorage(CITY_STORAGE_KEY, city)
    this.setData({ cityIndex: idx, selectedDate: '', selectedColor: '' }, () => {
      this._applyFilters()
      this.buildCalendar()
    })
  },

  onTypeChange(e) {
    const idx = Number(e.detail.value) || 0
    this._writeStorage(TYPE_STORAGE_KEY, (this.data.typeOptions[idx] || {}).value || DEFAULT_STORE_TYPE)
    this.setData({ typeIndex: idx, selectedDate: '', selectedColor: '' }, () => {
      this._applyFilters()
      this.buildCalendar()
    })
  },

  // 生成日历网格 + 跨天持续线 + 当月/当天快闪
  buildCalendar() {
    const { viewYear, viewMonth, filteredStores, selectedDate } = this.data
    const firstOfMonth = dateOnly(new Date(viewYear, viewMonth - 1, 1))
    const lastOfMonth = dateOnly(new Date(viewYear, viewMonth, 0))

    // 月历第一周周日、最后一周周六
    const startOfFirstWeek = new Date(firstOfMonth)
    startOfFirstWeek.setDate(firstOfMonth.getDate() - firstOfMonth.getDay())
    const endOfLastWeek = new Date(lastOfMonth)
    endOfLastWeek.setDate(lastOfMonth.getDate() + (6 - lastOfMonth.getDay()))

    const weeks = []
    for (let cur = new Date(startOfFirstWeek); cur <= endOfLastWeek; cur.setDate(cur.getDate() + 7)) {
      const weekStart = dateOnly(new Date(cur))
      const weekEnd = dateOnly(new Date(cur))
      weekEnd.setDate(weekEnd.getDate() + 6)

      // 7 个格子
      const row = []
      for (let i = 0; i < 7; i++) {
        const d = new Date(weekStart)
        d.setDate(d.getDate() + i)
        const inMonth = d.getMonth() + 1 === viewMonth
        const ds = dateStr(d)
        const dayStores = filteredStores.filter((s) => s.start && s.start <= d && d <= s.end)
        row.push({
          day: inMonth ? d.getDate() : null,
          dateStr: ds,
          fullDate: d,
          isToday: ds === this.data.todayStr,
          inMonth,
          hasEvent: dayStores.length > 0,
          colors: dayStores.slice(0, 3).map((s) => s.color),
          primaryColor: dayStores.length ? dayStores[0].color : '',
          selected: selectedDate === ds,
        })
      }

      // 跨天持续线：每个快闪在当前周的覆盖段
      const segments = []
      filteredStores.forEach((s) => {
        if (!s.start) return
        const segStart = s.start < weekStart ? weekStart : s.start
        const segEnd = s.end > weekEnd ? weekEnd : s.end
        if (segStart > segEnd) return
        segments.push({
          store: s,
          startCol: segStart.getDay(),
          endCol: segEnd.getDay(),
        })
      })

      // 分配轨道：同列不重叠的段可共享一行
      const tracks = []
      segments.forEach((seg) => {
        let placed = false
        for (let t = 0; t < tracks.length; t++) {
          const conflict = tracks[t].some((s) =>
            !(seg.endCol < s.startCol || seg.startCol > s.endCol)
          )
          if (!conflict) {
            tracks[t].push(seg)
            seg.track = t
            placed = true
            break
          }
        }
        if (!placed) {
          seg.track = tracks.length
          tracks.push([seg])
        }
      })

      const bars = segments.map((seg) => ({
        color: seg.store.color,
        title: seg.store.title,
        storeId: seg.store.id,
        left: (seg.startCol / 7 * 100).toFixed(3) + '%',
        width: ((seg.endCol - seg.startCol + 1) / 7 * 100).toFixed(3) + '%',
        top: (seg.track * 30 + 6) + 'rpx',
        showTitle: (seg.endCol - seg.startCol + 1) >= 2,
      }))

      const trackCount = tracks.length
      weeks.push({
        days: row,
        bars,
        trackCount,
        rowHeight: (110 + trackCount * 30) + 'rpx',
      })
    }

    // 当月快闪（与本月有重叠）——已按城市/类型过滤
    const monthStores = filteredStores.filter((s) => {
      if (!s.start) return false
      return s.end >= firstOfMonth && s.start <= lastOfMonth
    })

    // 可见列表：选中某天则只看当天，否则看整月
    let visibleStores = monthStores
    if (selectedDate) {
      const ds = parseISO(selectedDate)
      visibleStores = monthStores.filter((s) => s.start <= ds && ds <= s.end)
    }

    // 空态文案带上当前筛选条件，避免用户误以为「没有数据」
    const label = this.data.filterLabel
    const emptyText = selectedDate
      ? selectedDate + ' 这天没有符合条件的快闪店 🎌（' + label + '）'
      : '本月暂无符合条件的快闪店 🎌（' + label + '）'

    // 翻页边界：最小「上一个月」(-1)，最大「下两个月」(+2)
    const offset = this._monthOffset()
    this.setData({
      weeks,
      monthLabel: viewYear + '年' + viewMonth + '月',
      monthStores,
      visibleStores,
      emptyText,
      canPrev: offset > -1,
      canNext: offset < 2,
      loading: false,
    })
  },

  prevMonth() {
    // 不允许翻到比「当前月的上一个月」更早
    if (this._monthOffset() <= -1) return
    let { viewYear, viewMonth } = this.data
    viewMonth--
    if (viewMonth < 1) { viewMonth = 12; viewYear-- }
    this.setData({ viewYear, viewMonth, selectedDate: '', selectedColor: '' }, () => this.buildCalendar())
  },
  nextMonth() {
    // 不允许翻到比「当前月的下两个月」更晚
    if (this._monthOffset() >= 2) return
    let { viewYear, viewMonth } = this.data
    viewMonth++
    if (viewMonth > 12) { viewMonth = 1; viewYear++ }
    this.setData({ viewYear, viewMonth, selectedDate: '', selectedColor: '' }, () => this.buildCalendar())
  },
  goToday() {
    const now = dateOnly(new Date())
    this.setData({
      viewYear: now.getFullYear(),
      viewMonth: now.getMonth() + 1,
      selectedDate: this.data.todayStr,
      selectedColor: '',
    }, () => this.buildCalendar())
  },

  // 左右滑动切换月份
  onTouchStart(e) {
    this._tx = e.touches[0].clientX
    this._ty = e.touches[0].clientY
  },
  onTouchEnd(e) {
    if (this._tx === undefined) return
    const dx = e.changedTouches[0].clientX - this._tx
    const dy = e.changedTouches[0].clientY - this._ty
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.3) {
      if (dx < 0) this.nextMonth()
      else this.prevMonth()
    }
  },

  selectDay(e) {
    const dateStr = e.currentTarget.dataset.date
    const color = e.currentTarget.dataset.color
    if (!dateStr) return
    if (this.data.selectedDate === dateStr) {
      this.setData({ selectedDate: '', selectedColor: '' }, () => this.buildCalendar())
    } else {
      this.setData({ selectedDate: dateStr, selectedColor: color || '' }, () => this.buildCalendar())
    }
  },
  clearSelect() {
    this.setData({ selectedDate: '', selectedColor: '' }, () => this.buildCalendar())
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: '/pages/detail/detail?id=' + id })
  },
})
