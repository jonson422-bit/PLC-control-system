#!/bin/bash
# PLC 智能管控系统启动脚本

echo "🏭 PLC 智能管控系统"
echo "===================="

# 激活虚拟环境
source /home/pi/envs/plc_env/bin/activate

# 进入后端目录
cd /home/pi/OpenClaw_AI/extensions/plc-control/backend/plc_service

# 检查依赖
echo "📦 检查依赖..."
pip install -q fastapi uvicorn httpx 2>/dev/null

# 启动服务
echo "🚀 启动服务..."
echo ""
echo "访问地址:"
echo "  - Dashboard: http://192.168.1.16:8088"
echo "  - API Docs:  http://192.168.1.16:8088/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python main.py
