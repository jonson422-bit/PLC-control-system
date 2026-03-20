"""
点位管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from ..database import get_db, run_db, DB_PATH
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class PointConfig(BaseModel):
    name: str
    address: str
    data_type: str = "bit"
    description: Optional[str] = None
    unit: Optional[str] = None
    scale: Optional[float] = 1
    scale_low: Optional[float] = 0
    scale_high: Optional[float] = 27648
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    category: Optional[str] = "input"
    group_name: Optional[str] = None
    enabled: bool = True
    log_history: Optional[bool] = False


class PointUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    data_type: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    scale: Optional[float] = None
    scale_low: Optional[float] = None
    scale_high: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    category: Optional[str] = None
    group_name: Optional[str] = None
    enabled: Optional[bool] = None
    log_history: Optional[bool] = None


@router.get("")
async def list_points():
    """获取所有点位配置"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM points ORDER BY category, name")
            return [dict(row) for row in cursor.fetchall()]
    points = await run_db(_query)
    return {"points": points, "count": len(points)}


@router.get("/{point_id}")
async def get_point(point_id: int):
    """获取单个点位配置"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM points WHERE id = ?", (point_id,))
            return cursor.fetchone()
    row = await run_db(_query)
    if not row:
        raise HTTPException(status_code=404, detail="点位不存在")
    return dict(row)


@router.get("/name/{point_name}")
async def get_point_by_name(point_name: str):
    """通过名称获取点位配置"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM points WHERE name = ?", (point_name,))
            return cursor.fetchone()
    row = await run_db(_query)
    if not row:
        raise HTTPException(status_code=404, detail="点位不存在")
    return dict(row)


@router.post("")
async def create_point(point: PointConfig):
    """创建点位配置"""
    def _query():
        with get_db() as db:
            try:
                cursor = db.execute("""
                    INSERT INTO points (name, address, data_type, description, unit, scale_low, scale_high, category, group_name, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (point.name, point.address, point.data_type, point.description,
                      point.unit, point.scale_low, point.scale_high, point.category,
                      point.group_name, int(point.enabled)))
                db.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None
    point_id = await run_db(_query)
    if point_id is None:
        raise HTTPException(status_code=400, detail="点位名称已存在")
    return {"success": True, "id": point_id}


@router.put("/{point_id}")
async def update_point(point_id: int, point: PointUpdate):
    """更新点位配置"""
    def _query():
        with get_db() as db:
            # 检查是否存在
            cursor = db.execute("SELECT id FROM points WHERE id = ?", (point_id,))
            if not cursor.fetchone():
                return False
            
            # 构建更新语句
            updates = []
            params = []
            if point.name is not None:
                updates.append("name = ?")
                params.append(point.name)
            if point.address is not None:
                updates.append("address = ?")
                params.append(point.address)
            if point.data_type is not None:
                updates.append("data_type = ?")
                params.append(point.data_type)
            if point.description is not None:
                updates.append("description = ?")
                params.append(point.description)
            if point.unit is not None:
                updates.append("unit = ?")
                params.append(point.unit)
            if point.scale_low is not None:
                updates.append("scale_low = ?")
                params.append(point.scale_low)
            if point.scale_high is not None:
                updates.append("scale_high = ?")
                params.append(point.scale_high)
            if point.category is not None:
                updates.append("category = ?")
                params.append(point.category)
            if point.group_name is not None:
                updates.append("group_name = ?")
                params.append(point.group_name)
            if point.enabled is not None:
                updates.append("enabled = ?")
                params.append(int(point.enabled))
            
            if updates:
                params.append(point_id)
                db.execute(f"UPDATE points SET {', '.join(updates)} WHERE id = ?", params)
                db.commit()
            return True
    
    success = await run_db(_query)
    if not success:
        raise HTTPException(status_code=404, detail="点位不存在")
    return {"success": True, "message": "点位已更新"}


@router.delete("/{point_id}")
async def delete_point(point_id: int):
    """删除点位配置"""
    def _query():
        with get_db() as db:
            # 先删除监控配置中的关联
            db.execute("DELETE FROM monitor_config WHERE point_id = ?", (point_id,))
            # 再删除点位
            cursor = db.execute("DELETE FROM points WHERE id = ?", (point_id,))
            db.commit()
            return cursor.rowcount
    rowcount = await run_db(_query)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="点位不存在")
    return {"success": True, "message": "点位已删除"}


# ========== 监控变量配置 API ==========

@router.get("/monitor/list")
async def get_monitor_points():
    """获取监控变量列表"""
    def _query():
        with get_db() as db:
            cursor = db.execute("""
                SELECT mc.id, mc.point_id, mc.display_order, p.name, p.address, p.data_type, p.description, p.unit, p.category,
                       p.scale_low, p.scale_high
                FROM monitor_config mc
                JOIN points p ON mc.point_id = p.id
                ORDER BY mc.display_order, mc.id
            """)
            return [dict(row) for row in cursor.fetchall()]
    return await run_db(_query)


@router.post("/monitor/set")
async def set_monitor_points(point_ids: List[int]):
    """设置监控变量列表"""
    def _query():
        with get_db() as db:
            db.execute("DELETE FROM monitor_config")
            for idx, point_id in enumerate(point_ids):
                db.execute("""
                    INSERT INTO monitor_config (point_id, display_order)
                    VALUES (?, ?)
                """, (point_id, idx))
            db.commit()
            return True
    await run_db(_query)
    return {"success": True, "message": f"已设置 {len(point_ids)} 个监控变量"}


@router.post("/monitor/add/{point_id}")
async def add_monitor_point(point_id: int):
    """添加监控变量"""
    def _query():
        with get_db() as db:
            try:
                # 获取最大排序号
                cursor = db.execute("SELECT COALESCE(MAX(display_order), -1) FROM monitor_config")
                max_order = cursor.fetchone()[0]
                db.execute("""
                    INSERT INTO monitor_config (point_id, display_order)
                    VALUES (?, ?)
                """, (point_id, max_order + 1))
                db.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    success = await run_db(_query)
    if success:
        return {"success": True, "message": "已添加到监控列表"}
    else:
        return {"success": False, "message": "该点位已在监控列表中"}


@router.delete("/monitor/remove/{point_id}")
async def remove_monitor_point(point_id: int):
    """移除监控变量"""
    def _query():
        with get_db() as db:
            db.execute("DELETE FROM monitor_config WHERE point_id = ?", (point_id,))
            db.commit()
            return True
    await run_db(_query)
    return {"success": True, "message": "已从监控列表移除"}
