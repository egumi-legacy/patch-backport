FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    wget \
    vim \
    sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p data logs cache workspace results

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露API端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "core.api_service"] 