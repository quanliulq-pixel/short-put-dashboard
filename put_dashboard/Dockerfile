# Hugging Face Spaces / Render / Zeabur / Railway 通用免费云部署 Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 设置时区为北京时间 (Asia/Shanghai)
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1
# Hugging Face Spaces 默认监听 7860 端口
ENV PORT=7860

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# 确保数据缓存目录可写 (兼容 Hugging Face 非 root 容器权限)
RUN mkdir -p /app/data && chmod -R 777 /app/data

EXPOSE 7860

CMD ["sh", "-c", "gunicorn -w 2 --threads 4 -b 0.0.0.0:${PORT:-7860} --timeout 120 app:app"]
