"""
PLC 操作路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from plc_client import plc
from database import get_all_points, save_monitor_data

router = APIRouter()


class WriteRequest(BaseModel):
    point: str
    value: str | int


class CpuRequest(BaseModel):
    action: str  # start, stop


# 默认监控点位
DEFAULT_POINTS = [
    'I0.0', 'I0.1', 'I0.2', 'I0.3', 'I0.4', 'I0.5', 'I0.6', 'I0.7',
    'Q0.0', 'Q0.1', 'Q0.2', 'Q0.3', 'Q0.4', 'Q0.5', 'Q0.6', 'Q0.7',
    'AIW16', 'AIW18', 'AIW20', 'AIW22',
    'AQW32', 'AQW34'
]


@router.get("/read")
async def read_all():
    """读取所有监控点位"""
    if not plc.is_connected():
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    
    data = plc.read_all_points(DEFAULT_POINTS)
    return data


@router.get("/read/{point}")
async def read_point(point: str):
    """读取单个点位"""
    if not plc.is_connected():
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    
    data = plc.read_point(point)
    if not data.get('success'):
        raise HTTPException(status_code=400, detail=data.get('error', '读取失败'))
    
    # 保存到历史数据
    if 'raw_value' in data:
        save_monitor_data(point, data.get('value', 0), data['raw_value'])
    
    return data


@router.post("/write")
async def write_point(request: WriteRequest):
    """写入点位"""
    if not plc.is_connected():
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    
    result = plc.write_point(request.point, request.value)
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('error', '写入失败'))
    
    return result


@router.get("/status")
async def get_status():
    """获取 PLC 状态"""
    return {
        'connected': plc.is_connected(),
        'cpu_state': plc.get_cpu_state() if plc.is_connected() else 'DISCONNECTED',
        'ip': plc.ip
    }


@router.post("/cpu")
async def cpu_control(request: CpuRequest):
    """CPU 控制"""
    if not plc.is_connected():
        raise HTTPException(status_code=503, detail="PLC 连接不可用")
    
    if request.action.upper() == 'START':
        result = plc.cpu_start()
    elif request.action.upper() == 'STOP':
        result = plc.cpu_stop()
    else:
        raise HTTPException(status_code=400, detail="无效操作，支持 START 或 STOP")
    
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('error'))
    
    return result
