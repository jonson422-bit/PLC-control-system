"""
点位管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_all_points, get_point_by_name, get_history_data

router = APIRouter()


class PointConfig(BaseModel):
    name: str
    address: str
    data_type: str = "bit"
    description: Optional[str] = None
    unit: Optional[str] = None
    scale_low: Optional[float] = 0
    scale_high: Optional[float] = 27648
    category: Optional[str] = "input"


@router.get("")
async def list_points():
    """获取所有点位配置"""
    points = get_all_points()
    return {"points": points, "count": len(points)}


@router.get("/{point_name}")
async def get_point(point_name: str):
    """获取单个点位配置"""
    point = get_point_by_name(point_name)
    if not point:
        raise HTTPException(status_code=404, detail="点位不存在")
    return point


@router.get("/{point_name}/history")
async def get_history(point_name: str, hours: int = 24):
    """获取点位历史数据"""
    data = get_history_data(point_name, hours)
    return {"point": point_name, "data": data, "count": len(data)}
