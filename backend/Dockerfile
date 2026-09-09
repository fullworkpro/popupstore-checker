FROM python:3.11-slim

WORKDIR /app

# 安装依赖（先拷 requirements，利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
# scripts/ 必须进镜像：策展导入（import_curated.py）与场馆种子（seed_venues.py）
# 要在容器内用 `docker exec popstore-backend python scripts/xxx.py` 执行
COPY app ./app
COPY scripts ./scripts
COPY run_crawler.py .

# 数据目录（SQLite 与上传图片都落在 /app/data 下，由 compose 卷持久化）
RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
