"""
系统设置路由 - 读写运行时配置
"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# 可热更新的配置项定义: (key, type, default, label, group)
CONFIG_SCHEMA = [
    # PLC 连接
    ("PLC_IP", "str", "192.168.2.1", "PLC IP 地址", "plc"),
    ("PLC_RACK", "int", "0", "PLC Rack", "plc"),
    ("PLC_SLOT", "int", "1", "PLC Slot", "plc"),
    # 后台任务间隔
    ("CONNECTION_MONITOR_INTERVAL", "int", "3", "连接检查间隔(秒)", "task"),
    ("DATA_PUSH_INTERVAL", "int", "1", "数据推送间隔(秒)", "task"),
    ("ALARM_MONITOR_INTERVAL", "int", "2", "告警检查间隔(秒)", "task"),
    ("ERROR_RETRY_INTERVAL", "int", "5", "错误重试间隔(秒)", "task"),
    ("DATA_SAVE_INTERVAL", "int", "60", "数据保存间隔(次)", "task"),
    ("DATA_RETENTION_DAYS", "int", "30", "数据保留天数", "task"),
    # AI
    ("OLLAMA_URL", "str", "http://localhost:11434", "Ollama 地址", "ai"),
    ("OLLAMA_MODEL", "str", "deepseek-r1:1.5b", "默认模型", "ai"),
]

# 引用 main 模块的全局变量（延迟导入避免循环）
_main_module = None


def _get_main():
    global _main_module
    if _main_module is None:
        from .. import main as m
        _main_module = m
    return _main_module


@router.get("/config")
async def get_config():
    """获取当前运行时配置"""
    m = _get_main()
    configs = []
    for key, dtype, default, label, group in CONFIG_SCHEMA:
        if key.startswith("PLC_"):
            val = getattr(m, key, default)
        elif key.startswith("OLLAMA_"):
            # 从 ai 路由读取
            from ..routes import ai as ai_mod
            if key == "OLLAMA_URL":
                val = ai_mod.OLLAMA_URL
            else:
                val = ai_mod.DEFAULT_MODEL
        elif key == "AUTH_TOKEN":
            val = m.AUTH_TOKEN
            # 隐藏 token，只显示是否启用
            val = "****" if val else ""
        else:
            # 优先从 main 模块运行时变量读取，其次从环境变量
            val = getattr(m, key, None)
            if val is None:
                val = os.getenv(key, default)
        configs.append({
            "key": key,
            "value": val,
            "type": dtype,
            "default": default,
            "label": label,
            "group": group,
        })
    return {"configs": configs}


class ConfigUpdate(BaseModel):
    key: str
    value: str


@router.put("/config")
async def update_config(req: ConfigUpdate):
    """更新配置项并热加载"""
    key = req.key
    value = req.value.strip()
    schema = {s[0]: s for s in CONFIG_SCHEMA}
    if key not in schema:
        raise HTTPException(status_code=400, detail=f"不支持修改的配置项: {key}")

    _, dtype, default, label, group = schema[key]
    # 类型转换
    try:
        if dtype == "int":
            value = str(int(value))
        # str 类型保持原样
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 必须是整数")

    m = _get_main()

    # 更新运行时变量
    plc_changed = False
    if key == "PLC_IP":
        m.PLC_IP = value
        plc_changed = True
    elif key == "PLC_RACK":
        m.PLC_RACK = int(value)
        plc_changed = True
    elif key == "PLC_SLOT":
        m.PLC_SLOT = int(value)
        plc_changed = True
    elif key.startswith("OLLAMA_"):
        from ..routes import ai as ai_mod
        if key == "OLLAMA_URL":
            ai_mod.OLLAMA_URL = value
        else:
            ai_mod.DEFAULT_MODEL = value
    else:
        # 定时器间隔类配置 - 直接更新全局变量
        if hasattr(m, key):
            setattr(m, key, int(value))

    # 更新 .env 文件
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    _update_env_file(env_path, key, value)

    # PLC 参数变更 → 重连
    if plc_changed:
        logger.info(f"PLC 参数变更: IP={m.PLC_IP} Rack={m.PLC_RACK} Slot={m.PLC_SLOT}, 重连中...")
        m.plc_client.disconnect()
        m.plc_client.ip = m.PLC_IP
        m.plc_client.rack = m.PLC_RACK
        m.plc_client.slot = m.PLC_SLOT
        m.last_connection_state = None
        m.connection_alarm_sent = False

    return {"success": True, "key": key, "value": value, "label": label}


@router.post("/plc/reconnect")
async def plc_reconnect():
    """手动触发 PLC 重连"""
    m = _get_main()
    m.plc_client.disconnect()
    m.last_connection_state = None
    m.connection_alarm_sent = False
    return {"success": True, "message": f"正在重连 PLC ({m.PLC_IP})..."}


@router.get("/plc/reconnect")
async def plc_reconnect_get():
    """手动触发 PLC 重连（GET）"""
    return await plc_reconnect()


def _update_env_file(env_path: str, key: str, value: str):
    """更新 .env 文件中的配置项"""
    try:
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith(f"{key}="):
                        lines.append(f"{key}={value}\n")
                        found = True
                    elif stripped.startswith(f"# {key}="):
                        lines.append(f"{key}={value}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"{key}={value}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
    except Exception as e:
        logger.error(f"更新 .env 文件失败: {e}")
