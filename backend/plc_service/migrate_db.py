#!/usr/bin/env python3
"""
数据库迁移脚本：添加 STL 程序管理相关表
"""

import sqlite3
import os
import sys

# 添加当前目录到路径，以便导入 database 模块
sys.path.insert(0, os.path.dirname(__file__))
from database import DB_PATH

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. PLC程序表 — 使用中 (programs.json + 路由 /api/programs/)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plc_programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            original_name TEXT,
            content TEXT,
            plc_model TEXT DEFAULT 'S7-200 SMART',
            program_type TEXT DEFAULT 'STL',
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            variables_json TEXT,
            description TEXT,
            enabled INTEGER DEFAULT 1
        )
    """)

    # 2. 变量表（从STL解析出的变量）— 使用中 (routes/program_routes.py)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS program_variables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            variable_name TEXT NOT NULL,
            data_type TEXT NOT NULL,
            address TEXT,
            block_name TEXT,
            block_type TEXT,
            description TEXT,
            initial_value TEXT,
            is_monitored INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (program_id) REFERENCES plc_programs(id) ON DELETE CASCADE
        )
    """)

    # 3. 监控变量配置表 — 未使用 (已被 monitor_config 表取代，保留以防回退)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_variables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variable_id INTEGER NOT NULL,
            program_id INTEGER NOT NULL,
            monitor_name TEXT,
            sample_interval INTEGER DEFAULT 1000,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (variable_id) REFERENCES program_variables(id) ON DELETE CASCADE,
            FOREIGN KEY (program_id) REFERENCES plc_programs(id) ON DELETE CASCADE
        )
    """)

    # 4. 为知识库表添加 related_variables 字段
    try:
        cursor.execute("ALTER TABLE knowledge_base ADD COLUMN related_variables TEXT")
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_variables_program ON program_variables(program_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_variables_name ON program_variables(variable_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitored_var ON monitored_variables(variable_id)")

    # 5. 为 points 表添加缺失字段
    fields_to_add = [
        ("scale", "REAL DEFAULT 1.0"),
        ("min_value", "REAL"),
        ("max_value", "REAL"),
        ("log_history", "INTEGER DEFAULT 0"),
    ]
    
    for field_name, field_type in fields_to_add:
        try:
            cursor.execute(f"ALTER TABLE points ADD COLUMN {field_name} {field_type}")
            print(f"已添加字段: points.{field_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                pass  # 字段已存在
            else:
                print(f"添加字段 {field_name} 时出错: {e}")

    # 6. 系统配置表 — 未使用 (配置已迁移到 .env 文件，表保留备用)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE,
            config_value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 插入默认配置
    default_configs = [
        ("plc_ip", "192.168.2.1", "PLC IP 地址"),
        ("plc_rack", "0", "PLC Rack 编号"),
        ("plc_slot", "1", "PLC Slot 编号"),
        ("sample_interval", "1000", "采样间隔（毫秒）"),
        ("data_retention_days", "30", "历史数据保留天数"),
        ("feishu_enabled", "false", "是否启用飞书通知"),
    ]
    
    for key, value, desc in default_configs:
        cursor.execute("""
            INSERT OR IGNORE INTO system_config (config_key, config_value, description)
            VALUES (?, ?, ?)
        """, (key, value, desc))

    # 7. 操作日志表 — 未使用 (表已创建，功能待实现)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            target TEXT,
            details TEXT,
            user TEXT DEFAULT 'system',
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON operation_logs(created_at)")

    conn.commit()
    conn.close()
    print("数据库迁移完成！")

if __name__ == '__main__':
    migrate()
