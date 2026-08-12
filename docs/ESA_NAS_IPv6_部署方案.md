# 阿里云 ESA + NAS IPv6 部署方案

> 零服务器费用方案：利用阿里云 ESA（边缘安全加速）回源到家庭 NAS 的 IPv6 地址

## 架构概览

```
用户(微信小程序)
      │
      ▼
阿里云 ESA (边缘节点)
  - HTTPS 终结
  - 静态资源缓存
  - DDoS 防护
  - 智能路由
      │
      ▼ (回源)
家庭 NAS (IPv6)
  - Docker 运行 PopStore
  - Nginx + FastAPI + SQLite
  - 爬虫定时任务
```

## 前置条件

| 条件 | 说明 |
|------|------|
| 宽带支持 IPv6 | 目前三大运营商光猫默认开启 |
| NAS 有公网 IPv6 | 路由器开启 IPv6 防火墙允许特定端口 |
| 域名（已备案） | 微信小程序必须使用已备案域名 |
| 阿里云 ESA 服务 | 免费版或基础版 |
| DDNS 动态解析 | NAS 的 IPv6 地址可能变动 |

## 步骤一：NAS 端配置

### 1.1 获取 NAS IPv6 地址

```bash
# 在 NAS 上执行
ip -6 addr show scope global | grep -v temporary
# 记录 240e:xxxx:xxxx:xxxx::1 格式的地址
```

### 1.2 路由器配置

```
1. 登录路由器管理页面
2. 关闭 IPv6 防火墙 或 放行 80/443 端口
3. 保存设置
```

> ⚠️ 安全提醒：仅放行必要端口，建议配合 ESA 的 IP 白名单功能

### 1.3 DDNS 配置（解决 IPv6 变动问题）

```bash
# 在 NAS 上用 crontab 定期更新 DNS 记录
# 阿里云 DNS API 方式：
*/10 * * * * /usr/local/bin/aliyun-ddns.sh
```

### 1.4 Docker 部署 PopStore

```bash
# 在 NAS 上创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3'
services:
  popstore:
    image: python:3.11-slim
    container_name: popstore
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./data:/app/data
    working_dir: /app
    command: >
      sh -c "pip install -r requirements.txt &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000"
    restart: always
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/popstore.conf:/etc/nginx/conf.d/default.conf
      - ./admin-frontend/dist:/usr/share/nginx/html
    restart: always
EOF

docker-compose up -d
```

## 步骤二：阿里云 ESA 配置

### 2.1 添加站点

```
1. 登录阿里云 ESA 控制台
2. 添加站点 → 输入你的域名
3. 按指引修改 DNS 服务器
```

### 2.2 配置回源

```
源站类型：IP 地址
源站地址：你的 NAS IPv6 地址（如 240e:xxx:xxx:xxx::1）
回源端口：80
回源协议：HTTP（ESA 到 NAS 之间走 HTTP，用户到 ESA 走 HTTPS）
```

### 2.3 配置缓存规则

| 路径 | 缓存时间 | 说明 |
|------|---------|------|
| /static/* | 7天 | 上传的图片 |
| /assets/* | 30天 | 前端静态资源 |
| /api/* | 不缓存 | API 接口 |
| /index.html | 不缓存 | SPA 入口 |

### 2.4 配置 HTTPS

```
ESA 自动申请和管理 SSL 证书，无需额外配置
```

## 步骤三：微信小程序配置

```
小程序管理后台 → 开发 → 服务器域名：
- request合法域名：https://your-domain.com
```

## 费用对比

| 方案 | 月费用 | 年费用 |
|------|--------|--------|
| 云服务器方案 | 60-100元 | 720-1200元 |
| ESA + NAS IPv6 | ~0-5元 | ~0-60元 |

> ESA 免费版：每月 100 万次请求、10GB 流量（个人项目足够）
> 域名续费：约 50-70 元/年

## 注意事项

1. **IPv6 地址变动**：必须配置 DDNS，否则 ESA 回源失败
2. **NAS 稳定性**：家用 NAS 可能不如云服务器稳定，建议配置健康检查
3. **带宽限制**：家庭上行带宽通常较小（30-50Mbps），大流量场景可能不足
4. **备案要求**：微信小程序强制要求已备案域名 + HTTPS
5. **安全**：不要在 NAS 上开放不必要的端口，建议 ESA 设置 IP 访问控制
