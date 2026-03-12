"""
数据库模型和操作
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "plc_control.db"

def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 设备表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip_address TEXT NOT NULL DEFAULT '192.168.2.1',
            protocol TEXT DEFAULT 's7',
            rack INTEGER DEFAULT 0,
            slot INTEGER DEFAULT 1,
            connection_type INTEGER DEFAULT 3,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 点位配置表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL UNIQUE,
            address TEXT NOT NULL,
            data_type TEXT NOT NULL DEFAULT 'bit',
            description TEXT,
            unit TEXT,
            scale_low REAL DEFAULT 0,
            scale_high REAL DEFAULT 27648,
            category TEXT DEFAULT 'input',
            group_name TEXT,
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )
    """)
    
    # 监控数据表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            point_name TEXT NOT NULL,
            value REAL,
            raw_value INTEGER,
            quality TEXT DEFAULT 'good',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitor_timestamp ON monitor_data(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitor_point ON monitor_data(point_name)")
    
    # 告警规则表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alarm_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            point TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold REAL NOT NULL,
            severity TEXT DEFAULT 'warning',
            message TEXT,
            enabled INTEGER DEFAULT 1,
            cooldown_seconds INTEGER DEFAULT 60,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 告警事件表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alarm_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            point TEXT NOT NULL,
            value REAL,
            message TEXT,
            severity TEXT,
            status TEXT DEFAULT 'active',
            acknowledged_by TEXT,
            acknowledged_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rule_id) REFERENCES alarm_rules(id)
        )
    """)
    
    # 知识库表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT,
            related_points TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 插入默认设备
    cursor.execute("SELECT COUNT(*) FROM devices")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO devices (name, ip_address, protocol)
            VALUES ('S7-200 SMART', '192.168.2.1', 's7')
        """)
        
        # 插入默认点位
        default_points = [
            ('I0.0', 'PE:0:0', 'bit', '数字量输入0', None, 'input'),
            ('I0.1', 'PE:0:1', 'bit', '数字量输入1', None, 'input'),
            ('I0.2', 'PE:0:2', 'bit', '数字量输入2', None, 'input'),
            ('I0.3', 'PE:0:3', 'bit', '数字量输入3', None, 'input'),
            ('I0.4', 'PE:0:4', 'bit', '数字量输入4', None, 'input'),
            ('I0.5', 'PE:0:5', 'bit', '数字量输入5', None, 'input'),
            ('I0.6', 'PE:0:6', 'bit', '数字量输入6', None, 'input'),
            ('I0.7', 'PE:0:7', 'bit', '数字量输入7', None, 'input'),
            ('Q0.0', 'PA:0:0', 'bit', '数字量输出0', None, 'output'),
            ('Q0.1', 'PA:0:1', 'bit', '数字量输出1', None, 'output'),
            ('Q0.2', 'PA:0:2', 'bit', '数字量输出2', None, 'output'),
            ('Q0.3', 'PA:0:3', 'bit', '数字量输出3', None, 'output'),
            ('Q0.4', 'PA:0:4', 'bit', '数字量输出4', None, 'output'),
            ('Q0.5', 'PA:0:5', 'bit', '数字量输出5', None, 'output'),
            ('Q0.6', 'PA:0:6', 'bit', '数字量输出6', None, 'output'),
            ('Q0.7', 'PA:0:7', 'bit', '数字量输出7', None, 'output'),
            ('AIW16', 'PE:16', 'word', '温度传感器1', '°C', 'analog_in'),
            ('AIW18', 'PE:18', 'word', '温度传感器2', '°C', 'analog_in'),
            ('AIW20', 'PE:20', 'word', '温度传感器3', '°C', 'analog_in'),
            ('AIW22', 'PE:22', 'word', '温度传感器4', '°C', 'analog_in'),
            ('AQW32', 'PA:32', 'word', '模拟量输出1', None, 'analog_out'),
            ('AQW34', 'PA:34', 'word', '模拟量输出2', None, 'analog_out'),
        ]
        for point in default_points:
            cursor.execute("""
                INSERT INTO points (name, address, data_type, description, unit, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, point)
    
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# 点位操作
def get_all_points() -> List[Dict]:
    with get_db() as db:
        cursor = db.execute("SELECT * FROM points WHERE enabled = 1")
        return [dict(row) for row in cursor.fetchall()]


def get_point_by_name(name: str) -> Optional[Dict]:
    with get_db() as db:
        cursor = db.execute("SELECT * FROM points WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


# 告警规则操作
def get_alarm_rules() -> List[Dict]:
    with get_db() as db:
        cursor = db.execute("SELECT * FROM alarm_rules WHERE enabled = 1")
        return [dict(row) for row in cursor.fetchall()]


def create_alarm_rule(rule: Dict) -> int:
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO alarm_rules (name, point, operator, threshold, severity, message, cooldown_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (rule['name'], rule['point'], rule['condition']['operator'], 
              rule['condition']['value'], rule.get('severity', 'warning'),
              rule.get('message'), rule.get('cooldown_seconds', 60)))
        db.commit()
        return cursor.lastrowid


# 告警事件操作
def get_active_alarms() -> List[Dict]:
    with get_db() as db:
        cursor = db.execute("""
            SELECT ae.*, ar.name as rule_name 
            FROM alarm_events ae 
            LEFT JOIN alarm_rules ar ON ae.rule_id = ar.id
            WHERE ae.status = 'active'
            ORDER BY ae.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def create_alarm_event(event: Dict) -> int:
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO alarm_events (rule_id, point, value, message, severity)
            VALUES (?, ?, ?, ?, ?)
        """, (event.get('rule_id'), event['point'], event['value'], 
              event['message'], event.get('severity', 'warning')))
        db.commit()
        return cursor.lastrowid


def acknowledge_alarm(alarm_id: int, user: str = "system") -> bool:
    with get_db() as db:
        db.execute("""
            UPDATE alarm_events 
            SET status = 'acknowledged', acknowledged_by = ?, acknowledged_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (user, alarm_id))
        db.commit()
        return True


# 历史数据操作
def save_monitor_data(point_name: str, value: float, raw_value: int, quality: str = 'good'):
    with get_db() as db:
        db.execute("""
            INSERT INTO monitor_data (point_name, value, raw_value, quality)
            VALUES (?, ?, ?, ?)
        """, (point_name, value, raw_value, quality))
        db.commit()


def get_history_data(point_name: str, hours: int = 24) -> List[Dict]:
    with get_db() as db:
        cursor = db.execute("""
            SELECT * FROM monitor_data 
            WHERE point_name = ? 
            AND timestamp > datetime('now', ?)
            ORDER BY timestamp DESC
        """, (point_name, f'-{hours} hours'))
        return [dict(row) for row in cursor.fetchall()]


# 知识库操作
def search_knowledge(query: str, limit: int = 5) -> List[Dict]:
    with get_db() as db:
        cursor = db.execute("""
            SELECT * FROM knowledge_base 
            WHERE title LIKE ? OR content LIKE ? OR keywords LIKE ?
            LIMIT ?
        """, (f'%{query}%', f'%{query}%', f'%{query}%', limit))
        return [dict(row) for row in cursor.fetchall()]


def add_knowledge(item: Dict) -> int:
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO knowledge_base (category, title, content, keywords, related_points)
            VALUES (?, ?, ?, ?, ?)
        """, (item['category'], item['title'], item['content'],
              json.dumps(item.get('keywords', [])), 
              json.dumps(item.get('related_points', []))))
        db.commit()
        return cursor.lastrowid
