# PopStore Platform — 绿联云 NAS Docker 部署说明

> 本压缩包**只含非小程序部分**：FastAPI 后端 + 管理后台前端。小程序需单独用微信开发者工具发布，其 `apiBase` 改成下面「六、小程序连接」里的后端地址即可。

## 一、压缩包里有什么

```
popstore-docker/
├── backend/                 # 后端（FastAPI）
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run_crawler.py
│   ├── .dockerignore
│   └── app/                 # 全部后端源码
├── admin-frontend/          # 管理后台前端（Vue3 + nginx）
│   ├── Dockerfile
│   ├── nginx-docker.conf    # 已配好 /api、/static 反代到 backend
│   ├── package.json / package-lock.json
│   ├── vite.config.js / index.html
│   ├── .dockerignore
│   └── src/                 # 前端源码（API 用相对路径 /api/v1，无需改动）
├── compose.yml              # 编排文件（已针对绿联云优化）
└── README.md
```

已剔除：`node_modules`、`venv`、本地数据库 `data/`、 `__pycache__`、构建产物 `dist/` 等，体积很小（约 200KB）。

## 二、上传哪些文件

把**整个 `popstore-docker/` 目录**原样上传 / 复制到绿联云 NAS 即可（例如 `/volume1/docker/popstore/`）。后端和前端都通过 `Dockerfile` 在 NAS 上现场 `build`，不需要你本机的 `node_modules` 或 `venv`。

## 三、部署前必须修改的 env（在 `compose.yml` 的 `backend.environment` 段）

| 变量 | 默认值（要改） | 说明 |
|------|------|------|
| `SECRET_KEY` | `change-me-to-a-long-random-string` | **必须改**。JWT 签名密钥，随便写会被破解。生成命令：`openssl rand -hex 32` |
| `DEFAULT_ADMIN_PASSWORD` | `change-this-password` | **必须改**。默认管理员密码（用户名为 `admin`） |
| `DEBUG` | `false` | 生产保持 `false` |
| `DATABASE_URL` | `sqlite:///./data/popstore.db` | 一般不用改，SQLite 落在 `/app/data` 卷内 |
| `UPLOAD_DIR` | `/app/data/uploads` | 上传图片目录，一般不用改 |
| `TZ` | `Asia/Shanghai` | 时区，一般不用改 |

> 如果不用 Compose、而是在绿联云图形界面里手动建容器，同样在「环境变量」里填上以上这些键值对即可。

## 四、端口（在 `compose.yml` 的 `ports` 段）

- 后端：`9114:8000` → NAS 外部访问端口是左边的 `9114`（如需改外部端口只改左边，如 `"9000:8000"`）
- 前端：`9115:80` → 管理后台通过 `http://<NAS_IP>:9115` 访问
- 在绿联云 Docker 的「端口管理」里确认这两个端口已映射；要在手机/外网访问，还需在路由器做端口转发（或用 NAS 的远程访问 / 反代）。

## 五、数据持久化

backend 容器把 `/app/data` 映射到 NAS 目录：

```yaml
volumes:
  - ./data:/app/data
```

- `./data` 是相对路径（在 compose.yml 同目录下自动建 `data/` 文件夹）。
- **建议改成绿联云共享目录的真实绝对路径**，例如：
  ```yaml
  - /volume1/docker/popstore-platform/data:/app/data
  ```
  这样数据库（`popstore.db`）和上传图片（`uploads/`）都落在你能直接备份/迁移的位置，删容器、更镜像都不丢数据。当前示例路径为 `/volume1/docker/popstore-platform/data`。

## 六、用绿联云 Docker 部署

### 方案 A：项目 / Compose（推荐，UGOS Pro 支持）
1. 把 `popstore-docker/` 传到 NAS（如 `/volume1/docker/popstore/`）。
2. 绿联云 Docker → **项目**（或「Compose」）→ 创建项目 → 选择该目录 → 选 `compose.yml` → 确定。
3. 系统会自动 `build` 两个镜像并启动两个容器。
4. 浏览器打开 `http://<NAS_IP>:9115`，用 `admin` / 你设的密码登录。

### 方案 B：不支持 Compose 的旧版
1. 分别构建镜像：
   - 进 `backend/` 目录：`docker build -t popstore-backend .`
   - 进 `admin-frontend/` 目录：`docker build -t popstore-frontend .`
2. 在图形界面创建两个容器，依据 `compose.yml` 配：端口映射、环境变量（见第三节）、卷映射（见第五节）。
3. 启动后访问 `http://<NAS_IP>:9115`。

## 七、小程序连接（重要，非 Docker 部署范围但需配合）

小程序正式环境要能访问刚部署的后端，请在 `miniprogram/app.js` 修改 `apiBase`：

- **体验版 / 开发版**（仅局域网）：`http://<NAS局域网IP>:9114/api/v1`
- **正式版**：必须 HTTPS。在 NAS 或反向代理（如 Nginx/Caddy）上为域名配置证书，改成 `https://你的域名/api/v1`，并在微信公众平台「开发管理 → 服务器域名」里把该域名加入 **request 合法域名** 与 **downloadFile 合法域名**。
- 上传的图片走 `/static/...`，与后端同域，无需额外配置。

## 八、默认账号

- 用户名：`admin`
- 密码：你在 `DEFAULT_ADMIN_PASSWORD` 里设的值（首次启动自动创建；默认 `admin123` 仅本机开发用）

## 九、常用运维命令（SSH 进 NAS 后）

```bash
# 在 compose.yml 所在目录
docker compose ps                  # 查看容器状态
docker compose logs -f backend    # 看后端日志
docker compose restart            # 重启
docker compose up -d --build      # 改了代码后重新构建并启动
```
