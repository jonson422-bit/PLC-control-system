"""
设备管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..database import get_db, run_db
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class DeviceConfig(BaseModel):
    name: str
    ip_address: str = "192.168.2.1"
    protocol: str = "s7"
    rack: int = 0
    slot: int = 1
    enabled: bool = True


@router.get("")
async def list_devices():
    """获取所有设备"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM devices")
            return [dict(row) for row in cursor.fetchall()]
    devices = await run_db(_query)
    return {"devices": devices, "count": len(devices)}


@router.post("")
async def create_device(device: DeviceConfig):
    """创建设备"""
    def _query():
        with get_db() as db:
            cursor = db.execute("""
                INSERT INTO devices (name, ip_address, protocol, rack, slot, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device.name, device.ip_address, device.protocol,
                  device.rack, device.slot, int(device.enabled)))
            db.commit()
            return cursor.lastrowid
    device_id = await run_db(_query)
    return {"success": True, "device_id": device_id}


@router.get("/{device_id}")
async def get_device(device_id: int):
    """获取设备详情"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
            return cursor.fetchone()
    row = await run_db(_query)
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")
    return dict(row)


@router.put("/{device_id}")
async def update_device(device_id: int, device: DeviceConfig):
    """更新设备配置"""
    def _query():
        with get_db() as db:
            db.execute("""
                UPDATE devices SET name=?, ip_address=?, protocol=?, rack=?, slot=?, enabled=?
                WHERE id=?
            """, (device.name, device.ip_address, device.protocol,
                  device.rack, device.slot, int(device.enabled), device_id))
            db.commit()
    await run_db(_query)
    return {"success": True, "message": "设备已更新"}


@router.delete("/{device_id}")
async def delete_device(device_id: int, force: bool = False):
    """删除设备
    
    Args:
        device_id: 设备ID
        force: 是否强制删除（同时删除关联的点位数据）
    """
    def _check_and_delete():
        with get_db() as db:
            # 检查设备是否存在
            cursor = db.execute("SELECT name FROM devices WHERE id = ?", (device_id,))
            device = cursor.fetchone()
            if not device:
                return {"success": False, "error": "设备不存在", "status": 404}
            
            # 检查是否有关联的点位数据
            cursor = db.execute("SELECT COUNT(*) as count FROM points WHERE device_id = ?", (device_id,))
            point_count = cursor.fetchone()['count']
            
            if point_count > 0 and not force:
                return {
                    "success": False, 
                    "error": f"该设备有 {point_count} 个关联点位，请先删除点位或使用 force=true 强制删除",
                    "point_count": point_count,
                    "status": 409
                }
            
            # 执行删除
            if force and point_count > 0:
                # 先删除关联的点位
                db.execute("DELETE FROM monitor_config WHERE point_id IN (SELECT id FROM points WHERE device_id = ?)", (device_id,))
                db.execute("DELETE FROM points WHERE device_id = ?", (device_id,))
                logger.info(f"已删除设备 {device_id} 的 {point_count} 个关联点位")
            
            db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            db.commit()
            
            return {"success": True, "message": f"设备已删除", "deleted_points": point_count if force else 0}
    
    result = await run_db(_check_and_delete)
    
    if not result.get("success"):
        status = result.get("status", 400)
        raise HTTPException(status_code=status, detail=result.get("error"))
    
    return result


@router.post("/{device_id}/test")
async def test_connection(device_id: int):
    """测试设备连接"""
    def _query():
        with get_db() as db:
            cursor = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    device = await run_db(_query)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 测试连接 (在线程池中运行)
    def _test():
        from plc_client import PLCClient
        test_client = None
        try:
            test_client = PLCClient(device['ip_address'], device['rack'], device['slot'])
            connected = test_client.is_connected()
            return connected
        except Exception as e:
            logger.warning(f"设备连接测试失败: {e}")
            return False
        finally:
            # 确保无论如何都清理资源
            if test_client:
                try:
                    test_client.disconnect()
                except Exception as e:
                    logger.warning(f"断开测试连接时出错: {e}")
    
    connected = await asyncio.to_thread(_test)
    
    return {
        "success": connected,
        "device": device['name'],
        "ip": device['ip_address'],
        "message": "连接成功" if connected else "连接失败"
    }
