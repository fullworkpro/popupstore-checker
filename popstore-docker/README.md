# PopStore Platform — 绿联云 NAS Docker 部署说明

> 本目录**只含非小程序部分**：FastAPI 后端 + 管理后台前端（admin-frontend）。
> 小程序需单独用微信开发者工具发布，其 `apiBase` 改成「十、小程序连接」里的后端地址即可。
>
> 当前版本特性：后端 FastAPI + SQLite；管理后台支持门店 CRUD、拖拽排序、拖拽上传、七牛云 KODO 图床；后端提供部署指纹接口用于核对 NAS 上跑的是否为最新代码。

## 一、目录结构

```
popstore-docker/
├── backend/                     # 后端（FastAPI）
│   ├── Dockerfile
│   ├── requirements.txt         # 含 qiniu==7.11.1
│   ├── run_crawler.py
│   ├── .dockerignore
│   ├── .env.example             # 环境变量样例（含七牛占位）
│   └── app/
│       ├── main.py              # 入口：路由注册、/version.json、no-store 缓存头
│       ├── core/config.py       # 配置（含 APP_DEPLOY_TAG、七牛配置）
│       └── api/
│           ├── auth.py          # 登录 / 当前用户
│           ├── admin.py         # 后台管理（门店、上传、城市…）
│           ├── mini.py          # 小程序接口（门店列表/详情/轮播/城市/标签）
│           ├── proxy.py         # 本地图片代理（Cache-Control: max-age=86400）
│           ├── qiniu.py         # 七牛图床：GET /qiniu/uptoken、POST /qiniu/upload
│           └── version.py       # 部署指纹：GET /api/v1/version
├── admin-frontend/              # 管理后台前端（Vue3 + Vite + nginx）
│   ├── Dockerfile               # npm ci → npm run build → nginx 托管
│   ├── nginx-docker.conf        # /api、/static 反代到 backend；/static 7d 缓存
│   ├── package.json             # 含 vuedraggable
│   ├── public/version.json      # 前端部署指纹（source: frontend）
│   ├── src/
│   │   ├── api/index.js         # uploadImage 走 POST /qiniu/upload
│   │   └── views/StoreEdit.vue  # 图片拖拽排序 + 拖拽上传大区
│   └── …（vite.config.js / index.html / .dockerignore 等）
├── compose.yml                  # 编排文件（已针对绿联云优化，含七牛环境变量）
└── README.md
```

> `node_modules`、`venv`、本地数据库 `data/`、 `__pycache__`、构建产物 `dist/` 均已被 gitignore 排除，仓库体积很小。

## 二、上传哪些文件

把**整个 `popstore-docker/` 目录**原样上传 / 复制到绿联云 NAS 即可（例如 `/volume1/docker/popstore/`）。后端和前端都通过 `Dockerfile` 在 NAS 上现场 `build`，不需要你本机的 `node_modules` 或 `venv`。

## 三、部署前必须修改的 env（在 `compose.yml` 的 `backend.environment` 段）

### 3.1 基础（必须改）

| 变量 | 默认值（要改） | 说明 |
|------|------|------|
| `SECRET_KEY` | `change-me-to-a-long-random-string` | **必须改**。JWT 签名密钥。生成：`openssl rand -hex 32` |
| `DEFAULT_ADMIN_PASSWORD` | `change-this-password` | **必须改**。默认管理员密码（用户名为 `admin`） |
| `DEBUG` | `false` | 生产保持 `false` |
| `DATABASE_URL` | `sqlite:///./data/popstore.db` | 一般不用改，SQLite 落在 `/app/data` 卷内 |
| `UPLOAD_DIR` | `/app/data/uploads` | 上传图片目录，一般不用改 |
| `TZ` | `Asia/Shanghai` | 时区 |

### 3.2 七牛云 KODO 图床（必须填，否则图片上传功能不可用）

| 变量 | 示例值 | 说明 |
|------|------|------|
| `QINIU_ACCESS_KEY` | `__FILL_YOUR_QINIU_ACCESS_KEY__` | **部署时填真实 AK**（仓库内为占位符，勿提交明文） |
| `QINIU_SECRET_KEY` | `__FILL_YOUR_QINIU_SECRET_KEY__` | **敏感凭据，务必替换，切勿提交真实值** |
| `QINIU_BUCKET` | `popstore-img` | 存储空间名 |
| `QINIU_PUBLIC_DOMAIN` | `https://img.nas.ccxiang.top` | 公开访问域名（七牛 CDN 加速域名，已绑 HTTPS 证书） |
| `QINIU_UPLOAD_DOMAIN` | `https://upload-z2.qiniup.com` | 华南-广东 上传域名 |
| `QINIU_REGION` | `z2` | 区域：华南-广东 |
| `QINIU_TOKEN_EXPIRE` | `3600` | uptoken 有效期（秒） |

> 如果不用 Compose、而是在绿联云图形界面里手动建容器，同样在「环境变量」里填上以上键值对即可。

## 四、端口（在 `compose.yml` 的 `ports` 段）

- 后端：`9114:8000` → NAS 外部访问端口是左边的 `9114`（改外部端口只改左边，如 `"9000:8000"`）
- 前端：`9115:80` → 管理后台通过 `http://<NAS_IP>:9115` 访问
- 在绿联云 Docker 的「端口管理」里确认这两个端口已映射；要在手机/外网访问，还需在路由器做端口转发（或用 NAS 远程访问 / 反代）。

## 五、数据持久化

backend 容器把 `/app/data` 映射到 NAS 目录：

```yaml
volumes:
  - /volume1/docker/popstore-platform/data:/app/data
```

- 数据库（`popstore.db`）和上传图片（`uploads/`，仅本地兜底用，正常走七牛）都落在你能直接备份/迁移的位置，删容器、更镜像都不丢数据。
- 示例路径为 `/volume1/docker/popstore-platform/data`，请改成你 NAS 的真实绝对路径。

## 六、用绿联云 Docker 部署

### 方案 A：项目 / Compose（推荐，UGOS Pro 支持）
1. 把 `popstore-docker/` 传到 NAS（如 `/volume1/docker/popstore/`）。
2. 绿联云 Docker → **项目**（或「Compose」）→ 创建项目 → 选择该目录 → 选 `compose.yml` → 确定。
3. 系统会自动 `build` 两个镜像并启动两个容器。
4. 浏览器打开 `http://<NAS_IP>:9115`，用 `admin` / 你设的密码登录。

### 方案 B：不支持 Compose 的旧版
1. 分别构建镜像：
   - 进 `backend/`：`docker build -t popstore-backend .`
   - 进 `admin-frontend/`：`docker build -t popstore-frontend .`
2. 在图形界面创建两个容器，依据 `compose.yml` 配：端口映射、环境变量（见第三节）、卷映射（见第五节）。
3. 启动后访问 `http://<NAS_IP>:9115`。

## 七、七牛云 KODO 图床

- **存储空间**：`popstore-img`，区域 **华南-广东（z2）**，访问控制 **公开**。
- **CDN 加速域名**：`img.nas.ccxiang.top`（CNAME 指向 `*.qiniudns.com`，已在七牛侧绑定 HTTPS 证书）。
- **上传域名**：`upload-z2.qiniup.com`（小程序 `wx.uploadFile` 直传白名单用）。
- **架构**：
  - `SecretKey` **仅存在于后端环境变量**，绝不进前端。
  - `GET /qiniu/uptoken`：管理员鉴权后签发有时效的上传凭证（限 `image/*`、20MB）。
  - 小程序：拿 uptoken 后 `wx.uploadFile` 直传七牛。
  - 管理后台（admin-frontend）：`POST /qiniu/upload` 由后端代理直传，返回 `{url, key}`，前端 `uploadImage()` 已改走此接口。
- **Referer 防盗链必须关闭**：否则小程序 `<image>` 或外链加载 `img.nas.ccxiang.top` 图片会 403（浏览器因带白名单 Referer 能开，小程序因 Referer 为 `servicewechat.com` 被拦）。图床本就公开读 + CDN，关防盗链收益极低却专门卡小程序。

## 八、部署指纹 / 版本核对（确认 NAS 跑的是最新代码）

后端在启动时计算一次 `backend_fingerprint = sha256(main.py + api/qiniu.py + api/admin.py)`，并提供三个核对端点：

| 端点 | `source` | 内容 |
|------|----------|------|
| `GET https://<域名>/api/v1/version` | `backend` | `deploy_tag` + `backend_fingerprint` + `fingerprint_files` |
| `GET https://<域名>/version.json`（根路径） | `backend` | 同上，仅多 `source` 字段（与上一端点是同一进程、同一指纹） |
| `https://<域名>:9115/version.json`（前端静态） | `frontend` | 前端独立 `deploy_tag`，**不含 fingerprint** |

- 同一后端容器内，`/api/v1/version` 与 `/version.json` 的 `deploy_tag`、`backend_fingerprint` **必须完全相同**，只差一个 `source` 字段。
- 前端 `:9115/version.json` 的 `deploy_tag` 与后端**互不相干**（前端独立计数）。
- `APP_DEPLOY_TAG`（`config.py`）每次有意义的改动请手动 +1（如 `2026-08-27-admin-v4`），用于一眼识别部署批次。

**用法**：改完代码整体重建后，用下面命令核对两个后端端点指纹一致，即可确认 NAS 上跑的是最新代码；若仍返回旧 `deploy_tag` / 旧 `fingerprint`，说明旧容器未真正重建，或前方缓存层仍返回旧响应（见第九节）。

```bash
curl -s https://popstore.nas.ccxiang.top/api/v1/version | head
# 期望：{"app_version":"1.0.0","deploy_tag":"2026-08-27-admin-v4",
#        "backend_fingerprint":"<sha256>","fingerprint_files":["main.py","api/qiniu.py","api/admin.py"],"source":"backend"}
```

## 九、重要：API 域名走了阿里云 ESA，必须绕过缓存

**现象**：本地（绕过 ESA 直连后端）返回新值，但公网域名 `https://popstore.nas.ccxiang.top/api/v1/...` 返回旧数据。

**根因**：该域名经 **阿里云 ESA（边缘安全加速）** 边缘节点。后端默认不输出 `Cache-Control`，而 ESA 全局「边缘缓存过期时间」默认策略会在源站无缓存指令时套用默认规则，**把 `/api` 的 GET 响应缓存下来**，导致改了数据却看到旧内容。

**解决（ESA 控制台）**：

1. **立即清旧缓存**：站点管理 → 选 `popstore.nas.ccxiang.top` → **缓存 > 清除缓存**，清除 `https://popstore.nas.ccxiang.top/api/`（按前缀或按 URL 均可）。
2. **永久绕过（必做）**：**规则 > 缓存规则** → 新增规则：
   - 匹配：`http.host eq "popstore.nas.ccxiang.top"`（该域名只服务 API，无静态资源，整站绕过最干净）；或更精确：`URL 路径 包含 /api`（并补 `/version.json`）。
   - 缓存资格：**绕过缓存（Bypass Cache）**。
   - （可选）浏览器缓存过期时间：不缓存 / `no_cache`。
3. **（可选）查根因**：**缓存 > 配置 > 边缘缓存过期时间**，可把策略改为「否则不缓存」。

> ⚠️ ESA **不支持用 HTTP 响应头关闭缓存**，必须靠上面的 URL/主机路径规则。后端 `main.py` 虽已加 `Cache-Control: no-store` 作为兜底（对直连/其他代理有效），但在 ESA 这层不生效——**真正的开关是第九节的绕过缓存规则**。部署 `no-store` 改动仍建议执行（纵深防御），顺序建议：先 `docker compose up -d --build backend` 部署带 `no-store` 的新版，再去 ESA 清缓存 + 加绕过规则。

## 十、小程序连接（重要）

小程序正式环境要能访问刚部署的后端，请在 `miniprogram/app.js` 修改 `apiBase`：

- **体验版 / 开发版**（仅局域网）：`http://<NAS局域网IP>:9114/api/v1`
- **正式版**：必须 HTTPS。域名 `popstore.nas.ccxiang.top` 已在 ESA 配置证书；`apiBase` 改成 `https://popstore.nas.ccxiang.top/api/v1`。

**微信公众平台 → 开发管理 → 开发设置 → 服务器域名**（每行带 `https://`，不要结尾斜杠）：

| 字段 | 填写值 |
|------|--------|
| request 合法域名 | `https://popstore.nas.ccxiang.top` |
| uploadFile 合法域名 | `https://upload-z2.qiniup.com` |
| downloadFile 合法域名 | `https://popstore.nas.ccxiang.top;https://img.nas.ccxiang.top` |

- 详情页轮播图、封面图均从七牛 CDN `img.nas.ccxiang.top` 加载（故 `downloadFile` 必须含该域名，且七牛侧 Referer 防盗链已关闭，见第七节）。
- 小程序详情页「传图床」演示入口已移除（图床能力保留在 `utils/qiniu.js`，可复用）。

## 十一、默认账号

- 用户名：`admin`
- 密码：你在 `DEFAULT_ADMIN_PASSWORD` 里设的值（首次启动自动创建；默认 `admin123` 仅本机开发用）

## 十二、常用运维命令（SSH 进 NAS 后，在 compose.yml 所在目录）

```bash
docker compose ps                  # 查看容器状态
docker compose logs -f backend    # 看后端日志
docker compose restart            # 重启
docker compose up -d --build      # 改了代码后重新构建并启动（强制重建容器）
```

## 十三、安全注意事项

- `SECRET_KEY`、`QINIU_SECRET_KEY` **务必改为强随机串，且不要将真实值提交到仓库**。本仓库 `compose.yml` 中两者均为占位符（`__FILL_*`），部署时再填真实值；你的 NAS 运行副本是独立文件，不受影响。
- `QINIU_ACCESS_KEY` 同理建议用占位符管理，避免在公开/共享仓库泄露。
- 管理后台 `/admin/*`、七牛 `/qiniu/*` 均需管理员鉴权，请勿将后端端口 `9114` 直接暴露到公网而不加防护。
