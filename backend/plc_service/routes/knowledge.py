"""
知识库管理路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from .. import database as db
from ..database import run_db
import json
import os
import re

router = APIRouter()

# 上传目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "knowledge")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class KnowledgeItem(BaseModel):
    category: str = "general"
    title: str
    content: str
    keywords: List[str] = []
    related_points: List[str] = []


class KnowledgeUpdate(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[List[str]] = None
    related_points: Optional[List[str]] = None


def _parse_item(item):
    """解析知识条目的 JSON 字段"""
    item['keywords'] = json.loads(item.get('keywords', '[]'))
    item['related_points'] = json.loads(item.get('related_points', '[]'))
    return item


@router.get("/list")
async def list_knowledge(category: str = None):
    """获取知识库列表"""
    def _query():
        with db.get_db() as conn:
            if category:
                cursor = conn.execute(
                    "SELECT * FROM knowledge_base WHERE category = ? ORDER BY created_at DESC",
                    (category,)
                )
            else:
                cursor = conn.execute("SELECT * FROM knowledge_base ORDER BY created_at DESC")
            items = [_parse_item(dict(row)) for row in cursor.fetchall()]
            return items

    items = await run_db(_query)
    return {"items": items, "count": len(items)}


@router.get("/categories")
async def get_categories():
    """获取所有分类"""
    def _query():
        with db.get_db() as conn:
            cursor = conn.execute("SELECT DISTINCT category FROM knowledge_base")
            return [row['category'] for row in cursor.fetchall()]

    categories = await run_db(_query)
    return {"categories": categories}


@router.get("/{item_id}")
async def get_knowledge(item_id: int):
    """获取单条知识"""
    def _query():
        with db.get_db() as conn:
            cursor = conn.execute("SELECT * FROM knowledge_base WHERE id = ?", (item_id,))
            item = cursor.fetchone()
            if not item:
                return None
            return _parse_item(dict(item))

    item = await run_db(_query)
    if not item:
        raise HTTPException(status_code=404, detail="知识不存在")
    return item


@router.post("/add")
async def add_knowledge(item: KnowledgeItem):
    """添加知识"""
    def _query():
        with db.get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO knowledge_base (category, title, content, keywords, related_points)
                VALUES (?, ?, ?, ?, ?)
            """, (item.category, item.title, item.content,
                  json.dumps(item.keywords), json.dumps(item.related_points)))
            conn.commit()
            return cursor.lastrowid

    last_id = await run_db(_query)
    return {"id": last_id, "message": "添加成功"}


@router.put("/{item_id}")
async def update_knowledge(item_id: int, item: KnowledgeUpdate):
    """更新知识"""
    def _query():
        with db.get_db() as conn:
            # 检查是否存在
            cursor = conn.execute("SELECT id FROM knowledge_base WHERE id = ?", (item_id,))
            if not cursor.fetchone():
                return None

            # 构建更新语句
            updates = []
            params = []
            if item.category:
                updates.append("category = ?")
                params.append(item.category)
            if item.title:
                updates.append("title = ?")
                params.append(item.title)
            if item.content:
                updates.append("content = ?")
                params.append(item.content)
            if item.keywords is not None:
                updates.append("keywords = ?")
                params.append(json.dumps(item.keywords))
            if item.related_points is not None:
                updates.append("related_points = ?")
                params.append(json.dumps(item.related_points))

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(item_id)
                conn.execute(f"UPDATE knowledge_base SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()

            return True

    result = await run_db(_query)
    if result is None:
        raise HTTPException(status_code=404, detail="知识不存在")
    return {"message": "更新成功"}


@router.delete("/{item_id}")
async def delete_knowledge(item_id: int):
    """删除知识"""
    def _query():
        with db.get_db() as conn:
            cursor = conn.execute("DELETE FROM knowledge_base WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount

    rowcount = await run_db(_query)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="知识不存在")
    return {"message": "删除成功"}


@router.get("/search/{query}")
async def search_knowledge(query: str):
    """搜索知识"""
    def _query():
        results = db.search_knowledge(query)
        for item in results:
            _parse_item(item)
        return results

    results = await run_db(_query)
    return {"results": results}


@router.post("/upload")
async def upload_knowledge_file(file: UploadFile = File(...)):
    """上传知识库文件（JSON/Markdown）"""
    filename = file.filename.lower()

    if not (filename.endswith('.json') or filename.endswith('.md')):
        raise HTTPException(status_code=400, detail="仅支持 JSON 和 Markdown 文件")

    content = await file.read()

    try:
        if filename.endswith('.json'):
            # 解析 JSON 文件
            data = json.loads(content.decode('utf-8'))
            imported = await run_db(lambda: import_json_knowledge(data))
        else:
            # 解析 Markdown 文件
            imported = await run_db(lambda: import_markdown_knowledge(content.decode('utf-8'), filename))

        return {"message": f"成功导入 {imported} 条知识", "count": imported}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON 格式错误")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


def import_json_knowledge(data):
    """导入 JSON 格式的知识库（同步，需在线程池中调用）"""
    count = 0

    # 支持数组格式
    items = data if isinstance(data, list) else data.get('items', data.get('knowledge', []))

    with db.get_db() as conn:
        for item in items:
            if isinstance(item, dict) and 'title' in item and 'content' in item:
                conn.execute("""
                    INSERT INTO knowledge_base (category, title, content, keywords, related_points)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    item.get('category', 'general'),
                    item.get('title'),
                    item.get('content'),
                    json.dumps(item.get('keywords', [])),
                    json.dumps(item.get('related_points', []))
                ))
                count += 1
        conn.commit()

    return count


def import_markdown_knowledge(content, filename):
    """导入 Markdown 格式的知识库（同步，需在线程池中调用）"""
    count = 0
    lines = content.split('\n')

    current_item = None
    category = os.path.splitext(os.path.basename(filename))[0]

    with db.get_db() as conn:
        for line in lines:
            line = line.rstrip()

            # 检测标题（作为知识条目标题）
            if line.startswith('# ') and not line.startswith('## '):
                # 保存之前的条目
                if current_item and current_item.get('title') and current_item.get('content'):
                    conn.execute("""
                        INSERT INTO knowledge_base (category, title, content, keywords, related_points)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        current_item.get('category', category),
                        current_item['title'],
                        current_item['content'].strip(),
                        json.dumps(current_item.get('keywords', [])),
                        json.dumps(current_item.get('related_points', []))
                    ))
                    count += 1

                # 开始新条目
                current_item = {
                    'title': line[2:].strip(),
                    'content': '',
                    'category': category,
                    'keywords': [],
                    'related_points': []
                }

            # 检测分类标记
            elif line.startswith('**分类:**') or line.startswith('**分类：'):
                if current_item:
                    current_item['category'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()

            # 检测关键词标记
            elif line.startswith('**关键词:**') or line.startswith('**关键词：'):
                if current_item:
                    keywords_str = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    current_item['keywords'] = [k.strip() for k in keywords_str.split(',') if k.strip()]

            # 检测关联点位标记
            elif line.startswith('**关联点位:**') or line.startswith('**关联点位：'):
                if current_item:
                    points_str = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    current_item['related_points'] = [p.strip() for p in points_str.split(',') if p.strip()]

            # 普通内容行
            elif current_item and line and not line.startswith('---'):
                current_item['content'] += line + '\n'

        # 保存最后一个条目
        if current_item and current_item.get('title') and current_item.get('content'):
            conn.execute("""
                INSERT INTO knowledge_base (category, title, content, keywords, related_points)
                VALUES (?, ?, ?, ?, ?)
            """, (
                current_item.get('category', category),
                current_item['title'],
                current_item['content'].strip(),
                json.dumps(current_item.get('keywords', [])),
                json.dumps(current_item.get('related_points', []))
            ))
            count += 1

        conn.commit()

    return count


@router.post("/import/batch")
async def batch_import_knowledge(items: List[KnowledgeItem]):
    """批量导入知识"""
    def _query():
        count = 0
        with db.get_db() as conn:
            for item in items:
                conn.execute("""
                    INSERT INTO knowledge_base (category, title, content, keywords, related_points)
                    VALUES (?, ?, ?, ?, ?)
                """, (item.category, item.title, item.content,
                      json.dumps(item.keywords), json.dumps(item.related_points)))
                count += 1
            conn.commit()
        return count

    count = await run_db(_query)
    return {"message": f"成功导入 {count} 条知识", "count": count}
