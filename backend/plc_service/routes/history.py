"""
历史数据路由
"""
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
from typing import Optional
import csv
import io
from ..database import get_db, run_db

router = APIRouter()


@router.get("/point/{point}")
async def get_point_history(
    point: str,
    hours: int = Query(24, ge=1, le=720, description="查询时长（小时）"),
    interval: int = Query(60, ge=10, le=3600, description="采样间隔（秒）")
):
    """获取点位历史数据（按点位名称/地址查询）"""
    start_time = datetime.now() - timedelta(hours=hours)

    def _query():
        with get_db() as db:
            cursor = db.execute("""
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
            return [dict(row) for row in cursor.fetchall()]

    rows = await run_db(_query)

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
    start_time = datetime.now() - timedelta(hours=hours)

    def _query():
        with get_db() as db:
            all_data = {}
            for pt in point_list:
                cursor = db.execute("""
                    SELECT value, raw_value, timestamp
                    FROM monitor_data
                    WHERE point_name = ?
                    AND timestamp >= ?
                    ORDER BY timestamp ASC
                """, (pt, start_time.isoformat()))
                all_data[pt] = [dict(row) for row in cursor.fetchall()]
            return all_data

    all_rows = await run_db(_query)

    # 按间隔采样
    result = {}
    for point, rows in all_rows.items():
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
    start_time = datetime.now() - timedelta(hours=hours)

    def _query():
        with get_db() as db:
            cursor = db.execute("""
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
            return dict(row) if row else None

    row = await run_db(_query)

    if not row:
        return {
            'point': point,
            'hours': hours,
            'count': 0,
            'min_value': None,
            'max_value': None,
            'avg_value': None,
            'first_time': None,
            'last_time': None
        }

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
    cutoff_time = datetime.now() - timedelta(days=days)

    def _query():
        with get_db() as db:
            cursor = db.execute("""
                DELETE FROM monitor_data
                WHERE timestamp < ?
            """, (cutoff_time.isoformat(),))
            db.commit()
            return cursor.rowcount

    deleted_count = await run_db(_query)

    return {
        'success': True,
        'deleted_count': deleted_count,
        'message': f'已删除 {days} 天前的 {deleted_count} 条历史数据'
    }


@router.get("/export")
async def export_history_csv(
    point: str = Query(..., description="点位名称/地址"),
    hours: int = Query(24, ge=1, le=720, description="导出时长（小时）")
):
    """导出点位历史数据为 CSV（流式响应）"""
    start_time = datetime.now() - timedelta(hours=hours)

    def _query():
        with get_db() as db:
            cursor = db.execute("""
                SELECT point_name, value, raw_value, quality, timestamp
                FROM monitor_data
                WHERE point_name = ?
                AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (point, start_time.isoformat()))
            return cursor.fetchall()

    rows = await run_db(_query)

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        # 写入 BOM 和表头
        yield '\ufeff'
        writer.writerow(['timestamp', 'point', 'value', 'raw_value', 'quality'])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for row in rows:
            writer.writerow([
                row['timestamp'],
                row['point_name'],
                row['value'],
                row['raw_value'],
                row['quality']
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    filename = f"{point}_{hours}h_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
