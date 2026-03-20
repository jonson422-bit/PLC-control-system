#!/bin/bash
# PLC 智能管控系统启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/backend"
SERVICE_DIR="$PROJECT_DIR/plc_service"
VENV_DIR="/home/pi/envs/plc_env"
PID_FILE="/tmp/plc_service.pid"

echo "PLC 智能管控系统"
echo "===================="

# 检查虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 虚拟环境不存在: $VENV_DIR"
    exit 1
fi
source "$VENV_DIR/bin/activate"

# 检查项目目录
if [ ! -d "$SERVICE_DIR" ]; then
    echo "错误: 项目目录不存在: $SERVICE_DIR"
    exit 1
fi

# 检查端口是否被占用
PORT=8088
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "警告: 端口 $PORT 已被占用，尝试停止旧进程..."
    pkill -f "python.*plc_service" 2>/dev/null
    sleep 2
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo "错误: 端口 $PORT 仍被占用，请手动释放"
        exit 1
    fi
fi

cd "$PROJECT_DIR"

# 启动服务
echo "启动服务..."
echo ""
echo "访问地址:"
echo "  - Dashboard: http://$(hostname -I | awk '{print $1}' | head -1):$PORT"
echo "  - API Docs:  http://$(hostname -I | awk '{print $1}' | head -1):$PORT/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python -m plc_service.main
