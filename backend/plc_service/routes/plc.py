"""
PLC 操作路由 - 只读模式（安全保护）
写入功能已被移除，系统只能读取PLC数据，禁止任何写入操作
"""
from fastapi import APIRouter, HTTPException
from ..database import DEFAULT_POINTS, get_db  # 使用统一的默认点位定义
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# ============ 安全配置 ============
# 只读模式：系统只能读取PLC数据，禁止写入
READ_ONLY_MODE = True
# ==================================

# PLC 客户端引用（由 main.py 在启动时注入）
_plc_client = None


def set_plc_client(client):
    """注入 PLC 客户端实例（由 main.py 调用）"""
    global _plc_client
    _plc_client = client


def get_plc_client():
    if _plc_client is None:
        raise RuntimeError("PLC 客户端未初始化")
    return _plc_client


@router.get("/read")
async def read_all():
    """读取所有监控点位"""
    plc = get_plc_client()
    # 使用缓存的连接状态
    if not plc._connected:
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    try:
        return plc.read_all_points()
    except ConnectionError:
        raise HTTPException(status_code=503, detail="PLC 连接已断开")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"PLC 读取错误: {str(e)}")


@router.get("/read/{point}")
async def read_point(point: str):
    """读取单个点位"""
    plc = get_plc_client()
    if not plc._connected:
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    try:
        value = plc.read_point(point)
        if value is None:
            # 点位地址无法解析或读取失败
            raise HTTPException(status_code=400, detail=f"无法读取点位 {point}：地址无效或PLC返回空值")
        
        # 判断点位类型并格式化返回
        if '.' in point and (point.startswith('I') or point.startswith('Q')):
            # 位数据
            return {
                'point': point,
                'value': 'ON' if value else 'OFF',
                'raw_value': 1 if value else 0,
                'type': 'bit',
                'success': True
            }
        else:
            # 字数据（模拟量）- 查询换算参数
            scaled_value = None
            scale_low = 0
            scale_high = 27648
            try:
                with get_db() as db:
                    cursor = db.execute(
                        "SELECT scale_low, scale_high FROM points WHERE address = ? AND enabled = 1",
                        (point,)
                    )
                    row = cursor.fetchone()
                    if row and row['scale_high'] != 0:
                        scale_low = row['scale_low']
                        scale_high = row['scale_high']
                        scaled_value = round(scale_low + (value / scale_high) * (scale_high - scale_low), 2)
            except Exception:
                pass  # 查询失败不影响原始值返回
            return {
                'point': point,
                'value': value,
                'raw_value': value,
                'scaled_value': scaled_value,
                'scale_low': scale_low,
                'scale_high': scale_high,
                'type': 'analog',
                'success': True
            }
    except HTTPException:
        # 重新抛出已处理的异常
        raise
    except ConnectionError:
        raise HTTPException(status_code=503, detail="PLC 连接已断开")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"PLC 读取错误: {str(e)}")


@router.get("/status")
async def get_status():
    """获取 PLC 状态 - 使用缓存状态，避免阻塞"""
    plc = get_plc_client()
    return {
        'connected': plc._connected,
        'cpu_state': plc.get_cpu_state() if plc._connected else 'DISCONNECTED',
        'ip': plc.ip,
        'read_only_mode': READ_ONLY_MODE
    }


@router.get("/cpu")
async def get_cpu_info():
    """获取 PLC CPU 状态（只读）"""
    plc = get_plc_client()
    if not plc._connected:
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    return {
        'connected': True,
        'cpu_state': plc.get_cpu_state(),
        'read_only_mode': READ_ONLY_MODE,
        'message': '系统处于只读模式，写入操作已被禁止'
    }
