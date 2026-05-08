#!/bin/bash
set -e

echo ">>> 正在拉取 ElainaBot 镜像..."

# 尝试拉取 Docker Hub 镜像
if docker pull elainabot/elainabot:latest; then
    echo ">>> 镜像拉取成功"
    IMAGE="elainabot/elainabot:latest"
else
    echo ">>> Docker Hub 拉取失败，尝试本地构建..."
    
    # 克隆代码
    if [ ! -d "ElainaBot_v2_docker" ]; then
        git clone https://ghfast.top/https://github.com/3107410009/ElainaBot_v2_docker.git
    fi
    cd ElainaBot_v2_docker
    
    # 构建镜像
    docker build -t elainabot/elainabot:latest .
    IMAGE="elainabot/elainabot:latest"
fi

# 创建运行目录
mkdir -p ~/elainabot && cd ~/elainabot

# 下载 compose 文件（如果不存在）
if [ ! -f "docker-compose.yml" ]; then
    curl -fsSL -o docker-compose.yml https://ghfast.top/https://raw.githubusercontent.com/3107410009/ElainaBot_v2_docker/main/docker-compose.yml
fi

# 启动容器
echo ">>> 启动容器..."
docker compose up -d

echo ">>> 部署完成！"
echo ">>> 访问面板: http://$(hostname -I | awk '{print $1}'):5200/web/?token=admin"
echo ">>> 查看日志: docker compose logs -f"
echo ">>> 停止服务: docker compose down"
