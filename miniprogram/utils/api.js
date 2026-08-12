/**
 * 封装 wx.request 为 Promise
 * 每次请求时惰性读取 apiBase，确保能取到 app.js 中按环境切换后的地址
 */
const request = (url, options = {}) => {
  const apiBase = getApp().globalData.apiBase
  return new Promise((resolve, reject) => {
    wx.request({
      url: apiBase + url,
      method: options.method || 'GET',
      data: options.data || {},
      header: {
        'Content-Type': 'application/json',
        ...options.header,
      },
      success(res) {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject(res)
        }
      },
      fail(err) {
        reject(err)
      }
    })
  })
}

// 解析图片地址：
//  - 外链（http/https 开头）走后端同源代理 /api/v1/proxy-image，
//    绕过目标站防盗链与微信 downloadFile 合法域名限制（release 环境生效；
//    trial 局域网环境因微信不允许配置局域网域名为合法域名，外链图仍可能受限）
//  - 相对路径（如 /static/2026/08/12/xx.jpg，后端上传图存的就是这种）自动拼上后端主机，
//    这样小程序端也能正确加载（小程序无法解析无主机的相对路径）
const resolveImage = (url) => {
  if (!url) return ''
  if (/^https?:\/\//.test(url)) {
    const apiBase = (getApp().globalData && getApp().globalData.apiBase) || ''
    const base = apiBase.replace(/\/api\/v1\/?$/, '')
    return base + '/api/v1/proxy-image?url=' + encodeURIComponent(url)
  }
  const apiBase = (getApp().globalData && getApp().globalData.apiBase) || ''
  const base = apiBase.replace(/\/api\/v1\/?$/, '')
  return base + (url.startsWith('/') ? '' : '/') + url
}

// ── API 方法 ──

// 获取已发布的快闪店列表
const getStores = (params = {}) => {
  return request('/mini/stores', { data: params })
}

// 获取详情
const getStoreDetail = (id) => {
  return request(`/mini/stores/${id}`)
}

// 获取首页 Banner
const getBanners = () => {
  return request('/mini/banners')
}

// 获取城市列表
const getCities = () => {
  return request('/mini/cities')
}

// 获取标签列表
const getTags = () => {
  return request('/mini/tags')
}

module.exports = { getStores, getStoreDetail, getBanners, getCities, getTags, resolveImage }
