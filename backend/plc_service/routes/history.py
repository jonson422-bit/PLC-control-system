"""
历史数据路由
"""
from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from typing import Optional
import sqlite3
from pathlib import Path
from database import DB_PATH  # 使用统一的数据库路径

router = APIRouter()


@router.get("/point/{point}")
async def get_point_history(
    point: str,
    hours: int = Query(24, ge=1, le=720, description="查询时长（小时）"),
    interval: int = Query(60, ge=10, le=3600, description="采样间隔（秒）")
):
    """获取点位历史数据（按点位名称/地址查询）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询历史数据
    start_time = datetime.now() - timedelta(hours=hours)
    cursor.execute("""
        SELECT 
            point_name,
            value,
            raw_value,
            quality,
            timestamp
        FROM monitor_data
        WHERE point_name = ?
        AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (point, start_time.isoformat()))

    rows = cursor.fetchall()
    conn.close()

    # 按间隔采样
    data = []
    last_time = None
    for row in rows:
        row_time = datetime.fromisoformat(row['timestamp'])
        if last_time is None or (row_time - last_time).total_seconds() >= interval:
            data.append({
                'point': row['point_name'],
                'value': row['value'],
                'raw_value': row['raw_value'],
                'quality': row['quality'],
                'timestamp': row['timestamp']
            })
            last_time = row_time

    return {
        'point': point,
        'hours': hours,
        'count': len(data),
        'data': data
    }


@router.get("/batch")
async def get_multi_history(
    points: str = Query(..., description="点位列表，逗号分隔"),
    hours: int = Query(24, ge=1, le=720),
    interval: int = Query(60, ge=10, le=3600)
):
    """获取多个点位历史数据"""
    point_list = [p.strip() for p in points.split(',')]
    result = {}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_time = datetime.now() - timedelta(hours=hours)

    for point in point_list:
        cursor.execute("""
            SELECT value, raw_value, timestamp
            FROM monitor_data
            WHERE point_name = ?
            AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (point, start_time.isoformat()))

        rows = cursor.fetchall()

        # 按间隔采样
        data = []
        last_time = None
        for row in rows:
            row_time = datetime.fromisoformat(row['timestamp'])
            if last_time is None or (row_time - last_time).total_seconds() >= interval:
                data.append({
                    'value': row['value'],
                    'raw_value': row['raw_value'],
                    'timestamp': row['timestamp']
                })
                last_time = row_time

        result[point] = data

    conn.close()

    return {
        'hours': hours,
        'interval': interval,
        'points': result
    }


@router.get("/statistics/{point}")
async def get_point_statistics(
    point: str,
    hours: int = Query(24, ge=1, le=720)
):
    """获取点位统计信息"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start_time = datetime.now() - timedelta(hours=hours)

    cursor.execute("""
        SELECT 
            COUNT(*) as count,
            MIN(value) as min_value,
            MAX(value) as max_value,
            AVG(value) as avg_value,
            MIN(timestamp) as first_time,
            MAX(timestamp) as last_time
        FROM monitor_data
        WHERE point_name = ?
        AND timestamp >= ?
    """, (point, start_time.isoformat()))

    row = cursor.fetchone()
    conn.close()

    return {
        'point': point,
        'hours': hours,
        'count': row['count'],
        'min_value': row['min_value'],
        'max_value': row['max_value'],
        'avg_value': round(row['avg_value'], 2) if row['avg_value'] else None,
        'first_time': row['first_time'],
        'last_time': row['last_time']
    }


@router.delete("/cleanup")
async def clear_old_data(
    days: int = Query(30, ge=1, le=365, description="删除多少天前的数据")
):
    """清理旧历史数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff_time = datetime.now() - timedelta(days=days)

    cursor.execute("""
        DELETE FROM monitor_data
        WHERE timestamp < ?
    """, (cutoff_time.isoformat(),))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return {
        'success': True,
        'deleted_count': deleted_count,
        'message': f'已删除 {days} 天前的 {deleted_count} 条历史数据'
    }
