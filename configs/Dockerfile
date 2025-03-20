FROM ubuntu:22.04

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装内核编译依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    flex \
    bison \
    libssl-dev \
    libelf-dev \
    bc \
    ccache \
    git \
    kmod \
    python3 \
    ncurses-dev \
    rsync \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 配置ccache
RUN mkdir -p /ccache \
    && chmod 777 /ccache

RUN git clone --depth=1 https://github.com/gregkh/linux.git /kernel

# 设置工作目录
WORKDIR /kernel

# 设置环境变量
ENV PATH="/usr/lib/ccache:${PATH}" \
    CCACHE_DIR=/ccache \
    CCACHE_MAXSIZE=10G

# 入口点
ENTRYPOINT ["/bin/bash"]