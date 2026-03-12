"""
PLC 智能管控后端服务 - FastAPI 主程序
"""
import sys
sys.path.insert(0, '/home/pi/envs/plc_env/lib/python3.11/site-packages')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn

from database import init_db, get_db
from plc_client import PLCClient
from routes import plc, alarms, ai, points, devices

# 静态文件目录
STATIC_DIR = Path(__file__).parent / "static"

# 全局 PLC 客户端
plc_client = PLCClient()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    init_db()
    print("🚀 PLC Control Service starting...")
    print("📊 Database initialized")
    yield
    # 关闭时清理
    plc_client.disconnect()
    print("👋 PLC Control Service stopped")

app = FastAPI(
    title="PLC Control API",
    description="PLC智能管控系统后端API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(plc.router, prefix="/api/plc", tags=["PLC"])
app.include_router(alarms.router, prefix="/api/alarms", tags=["Alarms"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(points.router, prefix="/api/points", tags=["Points"])
app.include_router(devices.router, prefix="/api/devices", tags=["Devices"])


@app.get("/")
async def root():
    """返回 Dashboard 页面"""
    dashboard = STATIC_DIR / "dashboard.html"
    if dashboard.exists():
        return FileResponse(dashboard)
    return {"message": "PLC Control API", "version": "1.0.0"}


@app.get("/api")
async def api_info():
    """API 信息"""
    return {"message": "PLC Control API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "plc_connected": plc_client.is_connected()}


if __name__ == "__main__":
    print("🏭 PLC Control Service")
    print("📡 API: http://localhost:8088")
    print("📊 Dashboard: http://localhost:8088")
    print("📖 Docs: http://localhost:8088/docs")
    uvicorn.run(app, host="0.0.0.0", port=8088)
