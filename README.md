# PopStore Platform

> 二次元快闪店 · 门店与设备查询管理平台
> 管理后台（Vue3）+ 微信小程序 + FastAPI 后端，一键 Docker 部署到绿联云 NAS。

---

## 📌 项目简介

PopStore Platform 面向二次元（ACG）快闪店的设备查询与门店运营业务，提供三端协同：

- **管理后台**：运营人员维护快闪店 / 门店、查看爬虫采集数据；
- **微信小程序**：C 端用户浏览快闪店、查询设备、查看活动详情、收藏店铺；
- **后端服务**：统一管理后台与小程序的数据接口、多平台内容采集、图片代理与鉴权。

目标：让非技术人员也能在 NAS 上一键部署、自托管一套二次元快闪店运营与设备查询系统。

---

## ✨ 功能特性

### 管理后台（Vue3 + Element Plus）
- 快闪店 / 店铺管理（增删改查、起止时间、封面图）
- 仪表盘统计（Dashboard）
- 爬虫配置与日志查看（后台「爬虫」页面：开关 / 二次元 IP 关键词 / 排程 / Cookie + 手动触发 + 状态）
- JWT 登录鉴权
- 外链图片加载与**失败提示**（`SafeImage` 组件：加载失败显示明确错误而非空白）
- 图片上传到**图床**（拖拽大区，支持从其他标签页直接拖图；已上传图片可拖拽排序，首位为封面）

### 微信小程序（原生）
- 首页 / 列表 / 详情 / 收藏
- 正式环境 HTTPS 接入（域名需加入微信合法域名）

### 后端（FastAPI）
- 管理后台 API + 小程序 API（统一 `/api/v1`）
- **图床接入**（`app/api/qiniu.py`）：签发有时效的上传凭证（`GET /qiniu/uptoken`）并提供后端代理上传（`POST /qiniu/upload`），管理后台与小程序的图片统一存到图床
- **部署指纹**（`app/api/version.py`）：`GET /api/v1/version` 与 `GET /version.json` 返回 `deploy_tag` 与源码指纹，用于核对线上跑的是不是最新代码
- **API 不缓存**：对所有 `/api/*` 响应统一加 `Cache-Control: no-store`，避免改完数据仍显示旧内容
- 多平台内容爬虫：微博（全站搜索原创二次元快闪 + 时间窗追爬，详见下方「内容爬虫」）、微信 / 小红书 / 抖音（规划中）
- SQLite 存储，针对**网络共享卷**做了锁竞争加固（`busy_timeout` / `synchronous=NORMAL`）
- 同源图片代理 `GET /api/v1/proxy-image`，绕过外链防盗链 / 混合内容
- 容器时区正确（`tzdata` + `Asia/Shanghai`），爬虫定时不偏移
- 422 参数校验失败时在日志打印具体字段与请求体，便于排障

---

## 🧱 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI · SQLAlchemy · SQLite · Pydantic v2 · Uvicorn |
| 管理前端 | Vue3 · Element Plus · Vite · nginx |
| 小程序 | 微信原生（WXML / WXSS / JS） |
| 部署 | Docker · Docker Compose |

---

## 📁 目录结构

```
popstore-platform/
├── backend/              # FastAPI 后端源码（app/ 为全部业务代码）
├── admin-frontend/       # 管理后台前端（Vue3 + nginx）
├── miniprogram/          # 微信小程序（需单独用微信开发者工具发布）
├── popstore-docker/      # 部署包：compose.yml + 两个 Dockerfile + README
├── docs/
│   └── API.md            # 后端 API 文档
├── compose.yml           # 通用 Docker Compose（端口 9114/9115）
└── README.md             # 本文件（GitHub 首页）
```

> ⚠️ 部署请用 `popstore-docker/` 这个子目录（已剔除 `node_modules` / `venv` / `dist`，体积小）。小程序不在该包内，需单独发布。

---

## 🚀 快速部署（绿联云 NAS / 通用 Docker）

### 1. 上传部署包
把整个 `popstore-docker/` 目录上传 / 复制到 NAS，例如 `/volume1/docker/popstore-platform/`。

### 2. 修改环境变量（`popstore-docker/compose.yml` → `backend.environment`）

| 变量 | 默认值（需改） | 说明 |
|------|------|------|
| `SECRET_KEY` | `change-me-to-a-long-random-string` | **必须改**，JWT 签名密钥。生成：`openssl rand -hex 32` |
| `DEFAULT_ADMIN_PASSWORD` | `change-this-password` | **必须改**，默认管理员 `admin` 的密码 |
| `DEBUG` | `false` | 生产保持 `false` |
| `DATABASE_URL` | `sqlite:///./data/popstore.db` | 一般不用改，SQLite 落在 `/app/data` |
| `UPLOAD_DIR` | `/app/data/uploads` | 上传图片目录，一般不用改 |
| `TZ` | `Asia/Shanghai` | 时区，一般不用改 |
| `QINIU_*` | 见 `compose.yml` 注释 | 图床相关（AccessKey / SecretKey / Bucket / 域名等），按需填写 |

### 3. 数据目录（务必用真实绝对路径，便于备份迁移）

```yaml
volumes:
  - /volume1/docker/popstore-platform/data:/app/data
```

数据库 `popstore.db` 与上传图片 `uploads/` 都落在此目录。

### 4. 启动
- **绿联云 Docker → 项目 / Compose → 创建**，选择 `popstore-docker/compose.yml`；
- 或命令行：`cd popstore-docker && docker compose up -d --build`。

### 5. 访问

| 服务 | 地址 | 说明 |
|------|------|------|
| 管理后台 | `http://<NAS_IP>:9115` | 前端 nginx，自动反代 `/api` 到后端 |
| 后端 API | `http://<NAS_IP>:9114` | 直连后端；`/health` 返回 `{"status":"ok","db":"ok"}` |
| API 文档 | `http://<NAS_IP>:9114/docs` | FastAPI 自带 Swagger |

### 默认账号
- 用户名：`admin`
- 密码：你在 `DEFAULT_ADMIN_PASSWORD` 设置的值（首次启动自动创建）

### 常用运维命令
```bash
docker compose ps                   # 容器状态
docker compose logs -f backend     # 后端日志
docker compose restart             # 重启
docker compose up -d --build       # 改代码后重建并启动
```

---

## 📱 小程序接入

1. 在 `miniprogram/app.js` 修改 `apiBase`：
   - 开发 / 体验版（局域网）：`http://<NAS_IP>:9114/api/v1`
   - 正式版（**必须 HTTPS**）：`https://你的域名/api/v1`（该域名需在微信公众平台加入合法域名）
2. 微信公众平台 → 开发管理 → 服务器域名，把该 HTTPS 域名加入 **request 合法域名** 与 **downloadFile 合法域名**。
3. 用微信开发者工具上传为体验版 / 正式版。

> 上传图片走图床（与后端同链路），正式环境需在微信公众平台把图床域名加入 **downloadFile 合法域名**，否则图片在真机 / 审核时被拦截。

---

## 🔍 部署指纹核对

改完代码重建后，用以下方式确认线上跑的是不是最新版本：

```bash
# 后端指纹（同源两个端点，仅 source 字段不同）
curl https://你的域名/api/v1/version
curl https://你的域名/version.json
# 前端指纹（独立 deploy_tag）
curl https://你的域名:9115/version.json
```

- 后端两个端点应返回相同的 `deploy_tag` 与 `backend_fingerprint`；
- 若两个端点返回值不一致，说明有旧容器 / 缓存层在响应，需重建并清缓存。

---

## 🕷️ 内容爬虫（微博）

> 目标：自动发现「二次元快闪」动态，落入**待发布**（`status=draft`），由运营在后台补全 / 上传图片后发布。

### 抓取思路（为什么不用技能 / Playwright / 开放平台）
微博 Web 搜索与开放平台 API 均需登录或企业审核，成本高且易被限流。本项目直接使用 **m.weibo.cn 移动端 JSON 搜索接口**（`/api/container/getIndex?containerid=100103type=1&q=<关键词>`）对**全站公开内容**检索，无需登录、最轻量可靠。仅当服务器出口 IP 被微博 WAF 拦截（HTTP 432）时，才需在后台「爬虫」配置页填入浏览器 Cookie（首次种子仍可走 `CRAWLER_WEIBO_COOKIE` 环境变量）。

### 抓取逻辑（全站扫描，不限定账号）
1. 针对配置的**每个「二次元 IP 关键词」**（如 龙珠 / 原神 / 鸣潮 / chiikawa…）在微博全站搜索；
   - 名创优品等只是举例——本方案覆盖**全站所有品牌/IP**的二次元快闪，无需填写具体账号。
2. **仅保留原创微博**：跳过带 `retweeted_status` 的转发；
3. **过滤**：正文须含「快闪 / 快闪店」**且**命中某一 IP 关键词；
4. **时间窗追爬**：`since = 上次成功时刻`（无记录则回看 `CRAWLER_WEIBO_LOOKBACK_DAYS` 天），`until = 现在`；搜索结果按时间倒序，越界即停。
   - 每天定时 → 自然覆盖「前一天」；
   - 若连续多天未执行 → 窗口自动覆盖「上次成功 → 现在」，追爬遗漏的微博。
5. **解析**为待发布项：标题（首行 / 【】）、描述、原文链接、主办方（帖子作者）、图片直链（参考，需人工转存图床）、档期与城市/地址（尽量从正文正则提取）；
6. 落入 `stores` 表 `status=draft`。时间若只印在海报图上，标记 `needs_time`，由人工补全。

### 配置（在后台「爬虫」页面管理，无需改代码 / 环境变量）
所有爬虫配置均为**运行时可改**，存于数据库，由后台一级菜单「爬虫」页面维护：
- **启用开关**：关闭后定时任务跳过；
- **二次元 IP 关键词**：判定「二次元快闪」的 IP 名列表（龙珠 / 原神 / 鸣潮 / chiikawa…），可在页面增删；
- **每关键词搜索页数**：每个关键词最多翻几页搜索结果（平衡覆盖度与请求量）；
- **排程时刻**：每日自动执行的时刻（Asia/Shanghai），支持多个；
- **首次回看天数**：无历史成功记录时向前回看的天数；
- **微博 Cookie**：可选，仅当服务器 IP 被 WAF 拦截时填入（页面有获取指引，属敏感信息）。
> 环境变量 `CRAWLER_*` 仅作为首次建表时的**种子默认值**；之后一切以数据库（前端页面）为准，改完即时生效并自动调整定时任务。

### 触发方式（任选）
- **定时**：应用启动后由内置 APScheduler 按页面配置的「排程时刻」自动执行；开关关闭则跳过；
- **手动（仅微博）**：后台「爬虫」页「手动触发」按钮 → `POST /admin/crawler/weibo/run`；
- **手动（全部）**：`POST /admin/crawl/trigger`（或 `python run_crawler.py` 走系统 cron）；
- **查看状态**：后台「爬虫」页展示上次成功时间、待发布数、最近日志；接口 `GET /admin/crawler/config`；
- **待发布列表**：`GET /admin/stores?status=draft&source=weibo`，运营补全图片 / 时间后发布。

> **规划中**：微信 / **小红书** / **抖音** 监控已在前端「爬虫」页预留开关与凭据位，待微博爬虫验证通过后依次实现；当前调度会跳过未实现源。

---

## 📖 API 文档

完整接口见 [`docs/API.md`](docs/API.md)；运行后也可访问 `/docs`（Swagger）。

---

## 🗒️ 版本

### v1.2.2（本次）
- **微博爬虫改为全站扫描**：从「按账号时间线抓取」升级为**针对每个二次元 IP 关键词在全站搜索原创微博**，筛出正文含「快闪/快闪店」且命中 IP 的原创帖，覆盖全站所有品牌/IP（名创优品只是举例），不再限定单一账号。
- **关键词即 IP 名**：判定词从「二次元」等泛词改为具体 IP（龙珠 / 原神 / 鸣潮 / chiikawa…），可在页面增删。
- **Cookie 前端化 + 安全提示**：微博 Cookie 在后台「爬虫」页填写，附「如何获取 Cookie」指引与敏感信息警示；不再依赖 `compose.yml` 环境变量。
- **多源预留**：前端「爬虫」页新增小红书 / 抖音开关与凭据位（当前未实现，调度跳过），待微博验证通过后依次开放。
- **断点续爬 + 配置前端化**：延续 `crawler_state` 时间窗追爬；所有配置运行时存库、改完即时生效并自动调整定时任务。
- **后台接口补全**：`GET/PUT /admin/crawler/config`、`POST /admin/crawler/weibo/run`、`GET /admin/crawler/state`。

### 上一版
- **图床**：接入对象存储图床，管理后台与小程序图片统一上传到图床（`app/api/qiniu.py` 提供凭证签发与代理上传）；admin 上传区改为大拖拽区并支持已上传图片拖拽排序；小程序侧移除了详情页冗余的"传图床"演示入口。
- **部署指纹**：新增 `GET /api/v1/version` 与 `GET /version.json`，返回 `deploy_tag` 与源码指纹（前端另含独立的 `deploy_tag`），便于一条命令核对线上代码版本。
- **API 不缓存**：后端对所有 `/api/*` 响应加 `Cache-Control: no-store`，避免 CDN / 反向代理缓存导致数据更新后小程序仍显示旧内容。

---

## 📄 License

私有仓库，未经授权禁止二次分发。
