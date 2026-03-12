"""
设备管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
from database import get_db, DB_PATH

router = APIRouter()


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
    with get_db() as db:
        cursor = db.execute("SELECT * FROM devices")
        devices = [dict(row) for row in cursor.fetchall()]
    return {"devices": devices, "count": len(devices)}


@router.post("")
async def create_device(device: DeviceConfig):
    """创建设备"""
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO devices (name, ip_address, protocol, rack, slot, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (device.name, device.ip_address, device.protocol, 
              device.rack, device.slot, int(device.enabled)))
        db.commit()
        device_id = cursor.lastrowid
    return {"success": True, "device_id": device_id}


@router.get("/{device_id}")
async def get_device(device_id: int):
    """获取设备详情"""
    with get_db() as db:
        cursor = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="设备不存在")
        return dict(row)


@router.put("/{device_id}")
async def update_device(device_id: int, device: DeviceConfig):
    """更新设备配置"""
    with get_db() as db:
        db.execute("""
            UPDATE devices SET name=?, ip_address=?, protocol=?, rack=?, slot=?, enabled=?
            WHERE id=?
        """, (device.name, device.ip_address, device.protocol,
              device.rack, device.slot, int(device.enabled), device_id))
        db.commit()
    return {"success": True, "message": "设备已更新"}


@router.delete("/{device_id}")
async def delete_device(device_id: int):
    """删除设备"""
    with get_db() as db:
        db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        db.commit()
    return {"success": True, "message": "设备已删除"}


@router.post("/{device_id}/test")
async def test_connection(device_id: int):
    """测试设备连接"""
    from plc_client import PLCClient
    
    with get_db() as db:
        cursor = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="设备不存在")
        device = dict(row)
    
    # 测试连接
    test_client = PLCClient(device['ip_address'], device['rack'], device['slot'])
    connected = test_client.is_connected()
    test_client.disconnect()
    
    return {
        "success": connected,
        "device": device['name'],
        "ip": device['ip_address'],
        "message": "连接成功" if connected else "连接失败"
    }
