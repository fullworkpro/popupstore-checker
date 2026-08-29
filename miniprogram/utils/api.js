/**
 * 封装 wx.request 为 Promise
 * 每次请求时惰性读取 apiBase，确保能取到 app.js 中按环境切换后的地址
 */
const request = (url, options = {}) => {
  const apiBase = getApp().globalData.apiBase
  // 若本地 Storage 存有管理员令牌（运营在手机端调试图床时写入），自动带上
  const token = wx.getStorageSync('admin_token')
  const header = { 'Content-Type': 'application/json', ...options.header }
  if (token && !options.skipAuth) {
    header['Authorization'] = 'Bearer ' + token
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: apiBase + url,
      method: options.method || 'GET',
      data: options.data || {},
      header,
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
//  - 外链（http/https 开头）【直连】目标站，不经过 NAS 代理，多人访问不占 NAS 上行带宽；
//    （若正式版外链图加载失败，需在小程序后台「服务器域名」配置对应图片域名为合法域名）
//  - 相对路径（如 /static/2026/08/12/xx.jpg，后端上传图存的就是这种）自动拼上后端主机，
//    这样小程序端也能正确加载（小程序无法解析无主机的相对路径）
const resolveImage = (url) => {
  if (!url) return ''
  if (/^https?:\/\//.test(url)) {
    return url
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

// 获取七牛上传凭证（需管理员令牌；运营端调试时从 Storage 读取 admin_token）
const getQiniuUptoken = (ext = 'jpg') => {
  return request('/qiniu/uptoken?ext=' + ext)
}

module.exports = { getStores, getStoreDetail, getBanners, getCities, getTags, resolveImage, getQiniuUptoken }
