"""
数据库模型和操作
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from .logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent / "plc_control.db"

# 默认监控点位列表（统一管理）
DEFAULT_POINTS = [
    'I0.0', 'I0.1', 'I0.2', 'I0.3', 'I0.4', 'I0.5', 'I0.6', 'I0.7',
    'Q0.0', 'Q0.1', 'Q0.2', 'Q0.3', 'Q0.4', 'Q0.5', 'Q0.6', 'Q0.7',
    'AIW16', 'AIW18', 'AIW20', 'AIW22',
    'AQW32', 'AQW34'
]

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
            cooldown_seconds INTEGER DEFAULT 60,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 告警日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alarm_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            point TEXT NOT NULL,
            value REAL,
            message TEXT,
            severity TEXT DEFAULT 'warning',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rule_id) REFERENCES alarm_rules(id)
        )
    """)
    
    # 知识库表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            keywords TEXT,
            related_points TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    # 监控变量配置表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitor_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            point_id INTEGER NOT NULL,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (point_id) REFERENCES points(id),
            UNIQUE(point_id)
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
                INSERT OR IGNORE INTO points (name, address, data_type, description, unit, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, point)
    
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
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


def get_alarm_rule_by_id(rule_id: int) -> Optional[Dict]:
    with get_db() as db:
        cursor = db.execute("SELECT * FROM alarm_rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_alarm_rule(rule_id: int, rule: Dict) -> bool:
    with get_db() as db:
        db.execute("""
            UPDATE alarm_rules 
            SET name = ?, point = ?, operator = ?, threshold = ?, severity = ?, message = ?, cooldown_seconds = ?
            WHERE id = ?
        """, (rule['name'], rule['point'], rule['condition']['operator'],
              rule['condition']['value'], rule.get('severity', 'warning'),
              rule.get('message'), rule.get('cooldown_seconds', 60), rule_id))
        db.commit()
        return True


def delete_alarm_rule(rule_id: int) -> bool:
    with get_db() as db:
        db.execute("UPDATE alarm_rules SET enabled = 0 WHERE id = ?", (rule_id,))
        db.commit()
        return True


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


def get_alarms_by_status(status: str) -> List[Dict]:
    """按状态查询告警事件 (active/acknowledged/all)"""
    with get_db() as db:
        if status == 'all':
            cursor = db.execute("""
                SELECT ae.*, ar.name as rule_name
                FROM alarm_events ae
                LEFT JOIN alarm_rules ar ON ae.rule_id = ar.id
                ORDER BY ae.created_at DESC
            """)
        else:
            cursor = db.execute("""
                SELECT ae.*, ar.name as rule_name
                FROM alarm_events ae
                LEFT JOIN alarm_rules ar ON ae.rule_id = ar.id
                WHERE ae.status = ?
                ORDER BY ae.created_at DESC
            """, (status,))
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


def save_batch_monitor_data(data_list: list):
    """批量保存监控数据"""
    with get_db() as db:
        for item in data_list:
            db.execute("""
                INSERT INTO monitor_data (point_name, value, raw_value, quality)
                VALUES (?, ?, ?, ?)
            """, (item['point'], item['value'], item['raw_value'], item.get('quality', 'good')))
        db.commit()


def get_history_data(point_name: str, hours: int = 24) -> List[Dict]:
    """获取点位历史数据"""
    from datetime import datetime, timedelta
    start_time = datetime.now() - timedelta(hours=hours)
    
    with get_db() as db:
        cursor = db.execute("""
            SELECT * FROM monitor_data 
            WHERE point_name = ? 
            AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (point_name, start_time.isoformat()))
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


# ============== 告警规则操作（原生SQLite） ==============

def get_enabled_alarm_rules() -> List[Dict]:
    """获取所有启用的告警规则"""
    with get_db() as db:
        cursor = db.execute("""
            SELECT id, name, point, operator, threshold, severity, message, cooldown_seconds, enabled
            FROM alarm_rules
            WHERE enabled = 1
        """)
        return [dict(row) for row in cursor.fetchall()]


def create_alarm_log(rule_id: int, point: str, value: float, message: str, severity: str) -> int:
    """创建告警日志"""
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO alarm_logs (rule_id, point, value, message, severity, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (rule_id, point, value, message, severity))
        db.commit()
        return cursor.lastrowid


# 获取已配置的监控变量地址列表
def get_monitored_addresses() -> List[str]:
    """获取所有已启用监控变量的地址列表（从 monitor_config 表）"""
    with get_db() as db:
        cursor = db.execute("""
            SELECT DISTINCT p.address
            FROM monitor_config mc
            JOIN points p ON mc.point_id = p.id
            WHERE p.address IS NOT NULL AND p.address != ''
            ORDER BY mc.display_order
        """)
        return [row[0] for row in cursor.fetchall() if row[0]]


# 获取监控变量的完整配置（用于前端显示）
def get_monitored_points_config() -> List[Dict]:
    """获取监控变量的完整配置（包含点位详情）"""
    with get_db() as db:
        cursor = db.execute("""
            SELECT mc.id, mc.point_id, mc.display_order,
                   p.name, p.address, p.data_type, p.description, p.unit, p.category,
                   p.scale_low, p.scale_high
            FROM monitor_config mc
            JOIN points p ON mc.point_id = p.id
            ORDER BY mc.display_order, mc.id
        """)
        return [dict(row) for row in cursor.fetchall()]


# 监控变量配置操作 (monitor_config表)
def get_monitor_points() -> List[Dict]:
    """获取所有监控变量配置"""
    with get_db() as db:
        cursor = db.execute("""
            SELECT mc.id, mc.point_id, mc.display_order, p.name, p.address, p.data_type, p.description, p.unit, p.category,
                   p.scale_low, p.scale_high
            FROM monitor_config mc
            JOIN points p ON mc.point_id = p.id
            ORDER BY mc.display_order, mc.id
        """)
        return [dict(row) for row in cursor.fetchall()]


def add_monitor_point(point_id: int, display_order: int = 0) -> int:
    """添加监控变量"""
    with get_db() as db:
        try:
            cursor = db.execute("""
                INSERT INTO monitor_config (point_id, display_order)
                VALUES (?, ?)
            """, (point_id, display_order))
            db.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return -1  # 已存在
        except Exception as e:
            logger.error(f"添加监控变量失败: {e}")
            return -1


def remove_monitor_point(point_id: int) -> bool:
    """移除监控变量"""
    with get_db() as db:
        db.execute("DELETE FROM monitor_config WHERE point_id = ?", (point_id,))
        db.commit()
        return True


def set_monitor_points(point_ids: List[int]) -> bool:
    """设置监控变量列表（先清空再添加）"""
    with get_db() as db:
        db.execute("DELETE FROM monitor_config")
        for idx, point_id in enumerate(point_ids):
            db.execute("""
                INSERT INTO monitor_config (point_id, display_order)
                VALUES (?, ?)
            """, (point_id, idx))
        db.commit()
        return True


def is_point_monitored(point_id: int) -> bool:
    """检查点位是否在监控列表中"""
    with get_db() as db:
        cursor = db.execute("SELECT id FROM monitor_config WHERE point_id = ?", (point_id,))
        return cursor.fetchone() is not None
