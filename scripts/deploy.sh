#!/bin/bash
# PopStore Platform 一键部署脚本
# 适用于：Ubuntu 22.04+ / Debian 12+
set -e

APP_DIR="/opt/popstore"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/popstore"

echo "🚀 PopStore Platform 部署开始..."

# 创建目录
mkdir -p "$APP_DIR" "$LOG_DIR"

# Python 虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "✅ 虚拟环境已创建"
fi

source "$VENV_DIR/bin/activate"

# 安装后端依赖
pip install -r "$APP_DIR/backend/requirements.txt"
echo "✅ Python 依赖已安装"

# 构建前端
cd "$APP_DIR/admin-frontend"
if command -v pnpm &>/dev/null; then
    pnpm install && pnpm build
else
    npm install && npm run build
fi
echo "✅ 前端已构建"

# 复制 systemd 服务文件
cp "$APP_DIR/scripts/popstore-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable popstore-api
systemctl restart popstore-api
echo "✅ 后端服务已启动"

# 配置 crontab 爬虫定时任务
(crontab -l 2>/dev/null | grep -v "run_crawler.py" || true) > /tmp/crontab_tmp
echo "0 2 * * * cd $APP_DIR/backend && $VENV_DIR/bin/python3 run_crawler.py >> $LOG_DIR/crawler.log 2>&1" >> /tmp/crontab_tmp
echo "0 13 * * * cd $APP_DIR/backend && $VENV_DIR/bin/python3 run_crawler.py >> $LOG_DIR/crawler.log 2>&1" >> /tmp/crontab_tmp
crontab /tmp/crontab_tmp
rm /tmp/crontab_tmp
echo "✅ 爬虫定时任务已配置"

echo "🎉 部署完成！"
echo "   API 文档: http://your-server:8000/docs"
echo "   管理后台: http://your-server"
