# PopStore Platform API 文档

Base URL: `http://localhost:8000/api/v1`

## 认证

### POST /auth/login

管理员登录。

**Request:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "username": "admin"
}
```

所有管理后台接口需在 Header 中携带：
```
Authorization: Bearer {access_token}
```

---

## 后台管理 API

### GET /admin/dashboard
获取仪表盘统计数据。

### GET /admin/stores
快闪店列表，支持筛选。

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码，默认 1 |
| page_size | int | 每页数量，默认 20 |
| status | string | 状态筛选: draft/published/archived/rejected |
| city | string | 城市筛选 |
| source | string | 来源筛选 |
| keyword | string | 标题搜索 |

### POST /admin/stores
创建快闪店（草稿状态）。

### GET /admin/stores/{id}
获取快闪店详情。

### PUT /admin/stores/{id}
编辑快闪店。

### DELETE /admin/stores/{id}
删除快闪店。

### POST /admin/stores/{id}/review
审核快闪店。

```json
{
  "status": "published",
  "comment": "审核通过"
}
```

### POST /admin/upload
上传图片（multipart/form-data）。

### GET /admin/crawl-logs
爬虫日志列表。

### POST /admin/crawl/trigger
手动触发全部爬虫。

### GET /admin/crawler/config
获取爬虫配置与运行态（后台「爬虫」页面数据源）：启用开关、二次元 IP 关键词列表、每关键词搜索页数、排程时刻、回看天数、各平台是否含 Cookie，以及上次成功/运行时间、待发布(draft)条数、最近一次日志。

### PUT /admin/crawler/config
更新爬虫配置（运行时生效并自动调整定时任务）。请求体字段均可选：
- `enabled`：bool，总开关；
- `weibo_keywords`：`["龙珠","原神",...]`，二次元 IP 关键词（全站搜索用）；
- `weibo_max_pages`：int，每个关键词最多翻几页；
- `schedule`：`["HH:MM", ...]`（Asia/Shanghai）；
- `lookback_days`：int；
- `weibo_cookie`：string（可选，留空即清空）；
- `xhs_enabled` / `xhs_cookie`：小红书开关 / 凭据（规划中）；
- `douyin_enabled` / `douyin_cookie`：抖音开关 / 凭据（规划中）。

### POST /admin/crawler/weibo/run
仅触发微博爬虫（全站搜索原创二次元快闪 + 时间窗追爬，依据数据库配置），返回发现 / 新增条数。

### GET /admin/crawler/state
兼容接口：内容同 `GET /admin/crawler/config` 的运行态部分。

### GET /admin/cities
获取已有城市列表。

---

## 小程序 API（公开）

### GET /mini/banners
首页 Banner（最新 5 条已发布）。

### GET /mini/stores
已发布快闪店列表。

| 参数 | 说明 |
|------|------|
| page | 页码 |
| page_size | 每页数量 |
| city | 城市筛选 |
| keyword | 搜索关键词 |
| tag | 标签筛选 |
| sort | newest/hottest/ending_soon |

### GET /mini/stores/{id}
获取详情（自动增加浏览量）。

### GET /mini/cities
获取城市列表。

### GET /mini/tags
获取热门标签。
