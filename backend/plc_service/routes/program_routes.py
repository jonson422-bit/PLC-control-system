"""
程序管理路由 - STL程序上传、解析、管理
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

# 添加系统路径
import sys
sys.path.insert(0, '/home/pi/envs/plc_env/lib/python3.11/site-packages')

from ..stl_parser import STLParser
import sqlite3
import asyncio
from ..database import DB_PATH, run_db  # 使用统一的数据库路径
from ..logger import get_logger

router = APIRouter(tags=["Program"])
logger = get_logger(__name__)

# 上传目录 - 统一使用 plc_service/uploads/programs
UPLOAD_DIR = Path(__file__).parent.parent / "uploads" / "programs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 程序存储（简化版，使用JSON文件）
PROGRAMS_FILE = Path(__file__).parent.parent / "programs.json"


def load_programs():
    """加载程序列表"""
    if PROGRAMS_FILE.exists():
        with open(PROGRAMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"programs": [], "next_id": 1}


def save_programs(data):
    """保存程序列表"""
    with open(PROGRAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_program_id(data):
    """获取下一个程序ID（可靠的自增ID）"""
    # 使用存储的next_id，如果没有则从现有程序中计算最大ID+1
    if "next_id" in data and data["next_id"] > 0:
        return data["next_id"]
    
    # 兼容旧数据：从现有程序中计算最大ID
    existing_ids = [p.get("id", 0) for p in data.get("programs", [])]
    max_id = max(existing_ids) if existing_ids else 0
    return max_id + 1


@router.get("")
async def list_programs():
    """获取程序列表"""
    data = load_programs()
    programs = data.get("programs", [])
    return {"programs": programs, "count": len(programs)}


@router.post("/upload")
async def upload_program(file: UploadFile = File(...)):
    """上传并解析STL程序"""
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB 限制")

    # 检查文件类型
    if not file.filename.lower().endswith(('.stl', '.awl')):
        raise HTTPException(status_code=400, detail="只支持 .stl 或 .awl 文件")

    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_content = content.decode('gbk')
        except UnicodeDecodeError:
            try:
                text_content = content.decode('latin-1')
            except Exception as e:
                logger.warning(f"文件编码解码失败: {e}")
                text_content = content.decode('utf-8', errors='replace')

    # 生成唯一文件名（避免冲突）
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 清理文件名中的特殊字符
    safe_filename = "".join(c if c.isalnum() or c in '._-' else '_' for c in file.filename)
    unique_filename = f"{timestamp}_{safe_filename}"
    file_path = UPLOAD_DIR / unique_filename
    
    # 保存文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text_content)

    # 解析程序
    parser = STLParser()
    result = parser.parse(text_content)

    # 生成程序ID（使用可靠的自增ID）
    data = load_programs()
    program_id = get_next_program_id(data)
    data["next_id"] = program_id + 1  # 更新下一个ID

    # 提取变量列表 - 从解析结果的variables字段获取
    variables = []
    for var in result.get('variables', []):
        variables.append({
            'name': var.get('name', ''),
            'address': var.get('address', ''),
            'var_type': var.get('data_type', ''),
            'comment': var.get('description', ''),
            'block_name': var.get('block_name', '')
        })

    # 保存程序信息
    program_info = {
        'id': program_id,
        'name': file.filename,
        'path': str(file_path),
        'created_at': datetime.now().isoformat(),
        'variable_count': len(variables),
        'block_count': len(result.get('blocks', []))
    }
    data["programs"].append(program_info)
    save_programs(data)

    # 保存变量到单独文件
    vars_file = Path(__file__).parent.parent / f"program_{program_id}_vars.json"
    with open(vars_file, 'w', encoding='utf-8') as f:
        json.dump(variables, f, ensure_ascii=False, indent=2)

    return {
        'id': program_id,
        'name': file.filename,
        'message': '上传成功',
        'variable_count': len(variables),
        'block_count': len(result.get('blocks', []))
    }


@router.get("/{program_id}")
async def get_program(program_id: int):
    """获取程序详情和变量列表"""
    data = load_programs()

    # 查找程序
    program = None
    for p in data["programs"]:
        if p['id'] == program_id:
            program = p
            break

    if not program:
        raise HTTPException(status_code=404, detail="程序不存在")

    # 加载变量
    vars_file = Path(__file__).parent.parent / f"program_{program_id}_vars.json"
    variables = []
    if vars_file.exists():
        with open(vars_file, 'r', encoding='utf-8') as f:
            variables = json.load(f)

    return {
        'program': program,
        'variables': variables
    }


def _validate_path_within_dir(file_path: Path, base_dir: Path) -> bool:
    """验证文件路径在允许的目录内（防止路径遍历）"""
    try:
        file_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


@router.delete("/{program_id}")
async def delete_program(program_id: int):
    """删除程序"""
    data = load_programs()

    # 查找并删除程序
    for i, p in enumerate(data["programs"]):
        if p['id'] == program_id:
            # 删除文件（验证路径在允许目录内）
            file_path = Path(p.get('path', ''))
            if file_path.exists():
                if not _validate_path_within_dir(file_path, UPLOAD_DIR):
                    logger.warning(f"路径遍历攻击尝试: {file_path}")
                    raise HTTPException(status_code=400, detail="非法文件路径")
                file_path.unlink()

            # 删除变量文件（固定在项目目录内，program_id 为 int 类型安全）
            vars_file = Path(__file__).parent.parent / f"program_{program_id}_vars.json"
            if vars_file.exists():
                vars_file.unlink()

            # 从列表移除
            data["programs"].pop(i)
            save_programs(data)
            return {'message': '删除成功'}

    raise HTTPException(status_code=404, detail="程序不存在")


def get_address_category(address: str) -> str:
    """根据地址判断点位分类"""
    if not address:
        return 'memory'
    
    addr = address.upper().strip()
    
    if addr.startswith('I') and not addr.startswith('AIW'):
        return 'input'
    elif addr.startswith('Q') and not addr.startswith('AQW'):
        return 'output'
    elif addr.startswith('AIW'):
        return 'analog_in'
    elif addr.startswith('AQW'):
        return 'analog_out'
    elif addr.startswith(('M', 'V', 'SM', 'T', 'C')):
        return 'memory'
    else:
        return 'memory'


def get_data_type_from_var(var_type: str) -> str:
    """转换变量类型到点位数据类型"""
    type_map = {
        'BOOL': 'bool',
        'BYTE': 'byte',
        'WORD': 'word',
        'DWORD': 'dword',
        'INT': 'int',
        'DINT': 'dint',
        'REAL': 'real',
        'TIMER': 'timer',
        'COUNTER': 'counter',
    }
    return type_map.get(var_type.upper(), 'word')


class ImportVariablesRequest(BaseModel):
    """导入变量请求"""
    program_id: int
    variables: Optional[List[int]] = None  # 指定导入的变量索引，为空则导入全部
    overwrite: bool = False  # 是否覆盖已存在的点位


class VariableConfig(BaseModel):
    """变量配置"""
    name: str
    address: str
    var_type: str = "BOOL"
    comment: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    enabled: bool = True
    monitor: bool = True  # 是否启用监控


@router.post("/{program_id}/import")
async def import_variables_to_points(program_id: int, overwrite: bool = False):
    """将程序变量导入到点位配置表"""
    # 获取程序变量
    vars_file = Path(__file__).parent.parent / f"program_{program_id}_vars.json"
    if not vars_file.exists():
        raise HTTPException(status_code=404, detail="程序变量文件不存在")
    
    with open(vars_file, 'r', encoding='utf-8') as f:
        variables = json.load(f)
    
    # 过滤有有效地址的变量
    valid_vars = [v for v in variables if v.get('address') and v['address'].strip()]
    
    if not valid_vars:
        return {'success': False, 'message': '没有找到有效地址的变量', 'imported': 0}
    
    def _import_to_db():
        imported = 0
        skipped = 0
        updated = 0
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for var in valid_vars:
                address = var['address'].upper().strip()
                name = var.get('name', '') or address
                var_type = var.get('var_type', 'BOOL')
                comment = var.get('comment', '')
                category = get_address_category(address)
                data_type = get_data_type_from_var(var_type)
                
                # 检查是否已存在
                cursor.execute("SELECT id FROM points WHERE name = ? OR address = ?", (name, address))
                existing = cursor.fetchone()
                
                if existing:
                    if overwrite:
                        # 更新已存在的点位
                        cursor.execute("""
                            UPDATE points SET 
                                address = ?,
                                data_type = ?,
                                description = ?,
                                category = ?
                            WHERE id = ?
                        """, (address, data_type, comment, category, existing['id']))
                        updated += 1
                    else:
                        skipped += 1
                        continue
                else:
                    # 插入新点位
                    try:
                        cursor.execute("""
                            INSERT INTO points (name, address, data_type, description, category, enabled)
                            VALUES (?, ?, ?, ?, ?, 1)
                        """, (name, address, data_type, comment, category))
                        imported += 1
                    except sqlite3.IntegrityError:
                        skipped += 1
            
            conn.commit()
        
        return {'imported': imported, 'skipped': skipped, 'updated': updated}
    
    result = await run_db(_import_to_db)
    
    return {
        'success': True,
        'message': f'导入完成: 新增 {result["imported"]} 个, 更新 {result["updated"]} 个, 跳过 {result["skipped"]} 个',
        **result
    }


@router.post("/variables/import-selected")
async def import_selected_variables(
    variables: List[VariableConfig],
    overwrite: bool = False
):
    """批量导入选中的变量到点位配置"""
    if not variables:
        raise HTTPException(status_code=400, detail="变量列表不能为空")
    
    def _import_to_db():
        imported = 0
        skipped = 0
        updated = 0
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for var in variables:
                address = var.address.upper().strip()
                name = var.name or address
                category = var.category or get_address_category(address)
                data_type = get_data_type_from_var(var.var_type)
                
                # 检查是否已存在
                cursor.execute("SELECT id FROM points WHERE name = ? OR address = ?", (name, address))
                existing = cursor.fetchone()
                
                if existing:
                    if overwrite:
                        cursor.execute("""
                            UPDATE points SET 
                                address = ?,
                                data_type = ?,
                                description = ?,
                                category = ?,
                                unit = ?,
                                enabled = ?
                            WHERE id = ?
                        """, (address, data_type, var.comment, category, var.unit, int(var.enabled), existing['id']))
                        updated += 1
                    else:
                        skipped += 1
                        continue
                else:
                    try:
                        cursor.execute("""
                            INSERT INTO points (name, address, data_type, description, category, unit, enabled)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (name, address, data_type, var.comment, category, var.unit, int(var.enabled)))
                        imported += 1
                    except sqlite3.IntegrityError:
                        skipped += 1
            
            conn.commit()
        
        return {'imported': imported, 'skipped': skipped, 'updated': updated}
    
    result = await run_db(_import_to_db)
    
    return {
        'success': True,
        'message': f'导入完成: 新增 {result["imported"]} 个, 更新 {result["updated"]} 个, 跳过 {result["skipped"]} 个',
        **result
    }


@router.get("/{program_id}/variables")
async def get_program_variables(program_id: int):
    """获取程序变量列表（包含点位配置状态）"""
    vars_file = Path(__file__).parent.parent / f"program_{program_id}_vars.json"
    if not vars_file.exists():
        raise HTTPException(status_code=404, detail="程序变量文件不存在")
    
    with open(vars_file, 'r', encoding='utf-8') as f:
        variables = json.load(f)
    
    def _check_point_status():
        """检查变量是否已导入到点位表"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            for var in variables:
                if var.get('address'):
                    cursor.execute(
                        "SELECT id, name, data_type, description, unit, category, enabled FROM points WHERE address = ?", 
                        (var['address'].upper(),)
                    )
                    point = cursor.fetchone()
                    if point:
                        var['point_id'] = point['id']
                        var['point_name'] = point['name']
                        var['point_data_type'] = point['data_type']
                        var['point_description'] = point['description']
                        var['point_unit'] = point['unit']
                        var['point_category'] = point['category']
                        var['point_enabled'] = bool(point['enabled'])
                        var['imported'] = True
                    else:
                        var['point_id'] = None
                        var['imported'] = False
                        var['enabled'] = False
                else:
                    var['point_id'] = None
                    var['imported'] = False
                    var['enabled'] = False
        
        return variables

    result = await run_db(_check_point_status)
    
    return {
        'program_id': program_id,
        'variables': result,
        'count': len(result)
    }
