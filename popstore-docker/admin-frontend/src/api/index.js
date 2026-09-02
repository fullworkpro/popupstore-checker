import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器 — 自动带 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 — 统一错误处理
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.hash = '#/login'
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default api

// ── API 方法 ──

// 认证
export const loginApi = (data) => api.post('/auth/login', data)

// 仪表盘
export const getDashboard = () => api.get('/admin/dashboard')

// 快闪店
export const getStores = (params) => api.get('/admin/stores', { params })
export const getStore = (id) => api.get(`/admin/stores/${id}`)
export const createStore = (data) => api.post('/admin/stores', data)
export const updateStore = (id, data) => api.put(`/admin/stores/${id}`, data)
export const deleteStore = (id) => api.delete(`/admin/stores/${id}`)
export const reviewStore = (id, data) => api.post(`/admin/stores/${id}/review`, data)

// 上传
export const uploadImage = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/qiniu/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 爬虫
export const getCrawlerConfig = () => api.get('/admin/crawler/config')
export const updateCrawlerConfig = (data) => api.put('/admin/crawler/config', data)
export const runWeiboCrawler = () => api.post('/admin/crawler/weibo/run')
export const getCrawlLogs = (params) => api.get('/admin/crawl-logs', { params })
export const triggerCrawl = () => api.post('/admin/crawl/trigger')

// 城市列表
export const getCities = () => api.get('/admin/cities')
