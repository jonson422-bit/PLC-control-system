"""
AI 分析路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import json

router = APIRouter()

OLLAMA_URL = "http://localhost:11434"


class DiagnoseRequest(BaseModel):
    symptom: str
    context: Optional[str] = ""
    model: Optional[str] = "qwen2:7b"


class AnalyzeRequest(BaseModel):
    point: Optional[str] = None
    period: Optional[str] = "24h"
    model: Optional[str] = "qwen2:7b"


class RecommendRequest(BaseModel):
    focus: Optional[str] = "all"
    model: Optional[str] = "qwen2:7b"


async def call_ollama(prompt: str, model: str = "qwen2:7b") -> str:
    """调用 Ollama API"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                raise Exception(f"Ollama error: {response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI 服务不可用: {e}")


@router.post("/diagnose")
async def diagnose(request: DiagnoseRequest):
    """故障诊断"""
    from plc_client import plc
    from database import get_history_data
    
    # 获取当前状态
    current_state = {}
    if plc.is_connected():
        current_state = plc.get_cpu_state()
    
    prompt = f"""你是一位资深的 PLC 自动化工程师。请根据以下信息进行故障诊断。

故障现象: {request.symptom}
额外上下文: {request.context or '无'}
PLC 当前状态: {current_state}

请分析可能的故障原因，并给出具体的排查建议。回复格式：

## 可能原因
1. ...
2. ...

## 排查步骤
1. ...
2. ...

## 预防措施
- ...
"""
    
    analysis = await call_ollama(prompt, request.model)
    
    return {
        "symptom": request.symptom,
        "analysis": analysis,
        "model": request.model
    }


@router.get("/analyze")
async def analyze(point: Optional[str] = None, period: str = "24h"):
    """数据分析"""
    from database import get_history_data
    
    # 解析时间范围
    hours = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}.get(period, 24)
    
    # 获取历史数据
    data = []
    if point:
        data = get_history_data(point, hours)
    
    # 简单统计
    summary = "暂无足够数据进行分析"
    if data:
        values = [d['value'] for d in data if d.get('value') is not None]
        if values:
            summary = f"""
数据点数: {len(values)}
最大值: {max(values):.2f}
最小值: {min(values):.2f}
平均值: {sum(values)/len(values):.2f}
"""
    
    return {
        "point": point,
        "period": period,
        "data_count": len(data),
        "summary": summary
    }


@router.post("/recommend")
async def recommend(request: RecommendRequest):
    """优化建议"""
    from plc_client import plc
    
    # 获取当前状态
    status = {}
    if plc.is_connected():
        status = {
            "cpu_state": plc.get_cpu_state(),
            "connected": True
        }
    
    prompt = f"""你是一位资深的 PLC 自动化工程师。请基于以下信息给出优化建议。

关注点: {request.focus}
系统状态: {json.dumps(status, ensure_ascii=False)}

请从以下几个方面给出建议：
1. 能耗优化
2. 效率提升
3. 安全保障
4. 维护建议
"""
    
    recommendations = await call_ollama(prompt, request.model)
    
    return {
        "focus": request.focus,
        "recommendations": recommendations,
        "model": request.model
    }


@router.get("/knowledge")
async def search_knowledge(q: str, limit: int = 5):
    """搜索知识库"""
    from database import search_knowledge as db_search
    
    results = db_search(q, limit)
    return {"query": q, "results": results, "count": len(results)}


@router.post("/knowledge")
async def add_knowledge_item(item: dict):
    """添加知识"""
    from database import add_knowledge
    
    item_id = add_knowledge_item(item)
    return {"success": True, "id": item_id}
