FROM python:3.11-slim

WORKDIR /app

# 时区数据：slim 镜像默认不带 tzdata，glibc 读不到 zoneinfo 会回退 UTC，
# 导致 compose 里的 TZ=Asia/Shanghai 失效、定时爬虫整体偏移 8 小时。
# 显式安装 tzdata 并设为上海时区（Windows 本地开发因系统已是上海时区未暴露此问题）。
ENV TZ=Asia/Shanghai
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖（先拷 requirements，利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
COPY app ./app
COPY run_crawler.py .

# 数据目录（SQLite 与上传图片都落在 /app/data 下，由 compose 卷持久化）
RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
