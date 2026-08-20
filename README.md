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
- 爬虫日志查看（CrawlLogs）
- JWT 登录鉴权
- 外链图片加载与**失败提示**（`SafeImage` 组件：加载失败显示明确错误而非空白）

### 微信小程序（原生）
- 首页 / 列表 / 详情 / 收藏
- 正式环境 HTTPS 接入（域名需加入微信合法域名）

### 后端（FastAPI）
- 管理后台 API + 小程序 API（统一 `/api/v1`）
- 多平台内容爬虫：微信 / 微博 / 小红书（`run_crawler.py` 独立脚本）
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
   - 正式版（**必须 HTTPS**）：如 `https://popstore.nas.ccxiang.top/api/v1`
2. 微信公众平台 → 开发管理 → 服务器域名，把该 HTTPS 域名加入 **request 合法域名** 与 **downloadFile 合法域名**。
3. 用微信开发者工具上传为体验版 / 正式版。

> 上传图片走 `/static/...`，与后端同域，无需额外配置。

---

## 📖 API 文档

完整接口见 [`docs/API.md`](docs/API.md)；运行后也可访问 `/docs`（Swagger）。

---

## 🗒️ 版本

- **v1.1**（当前）：修复登录 30s 超时根因（移除导致 POST 挂起的 `BaseHTTPMiddleware`）、SQLite 网络挂载加固、Linux `tzdata` 时区、外链图片直连省带宽、小程序 HTTPS 域名适配。详见 [Releases](../../releases/tag/v1.1)。

---

## 📄 License

私有仓库，未经授权禁止二次分发。
