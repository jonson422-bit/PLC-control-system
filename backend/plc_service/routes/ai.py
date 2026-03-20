"""
AI 分析路由 - 结合知识库进行故障诊断
优化版：完善的错误处理和超时控制
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import httpx
import json
from .. import database as db
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-r1:1.5b"  # 使用最快的模型
AI_TIMEOUT = 120.0  # AI 响应超时时间（秒）


class DiagnoseRequest(BaseModel):
    symptom: str
    context: Optional[str] = ""
    model: Optional[str] = DEFAULT_MODEL


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    model: Optional[str] = DEFAULT_MODEL


class VariableInferRequest(BaseModel):
    """变量名推断请求"""
    code: str  # STL 代码
    variables: List[Dict]  # 已解析的变量列表
    model: Optional[str] = DEFAULT_MODEL


async def check_ollama_health() -> bool:
    """检查 Ollama 服务是否可用"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Ollama健康检查失败: {e}")
        return False


async def call_ollama(prompt: str, model: str = DEFAULT_MODEL) -> tuple:
    """调用 Ollama API，返回 (成功, 响应/错误信息)"""
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 800,
                        "temperature": 0.7
                    }
                }
            )
            if response.status_code == 200:
                return True, response.json().get("response", "")
            else:
                return False, f"AI 服务返回错误: {response.status_code}"
    except httpx.TimeoutException:
        return False, "AI 响应超时，请稍后重试"
    except httpx.ConnectError:
        return False, "AI 服务未启动，请检查 Ollama 是否运行"
    except Exception as e:
        return False, f"AI 服务异常: {str(e)}"


def get_knowledge_context(query: str, limit: int = 3) -> str:
    """从知识库获取相关内容"""
    try:
        results = db.search_knowledge(query, limit)
        if not results:
            return ""
        
        context = "\n\n## 相关知识库参考：\n"
        for i, item in enumerate(results, 1):
            keywords = json.loads(item.get('keywords', '[]'))
            context += f"""
### 参考{i}：{item['title']}
**分类:** {item.get('category', '通用')}
**关键词:** {', '.join(keywords)}
**内容:**
{item.get('content', '')[:500]}
---
"""
        return context
    except Exception as e:
        logger.error(f"知识库查询错误: {e}")
        return ""


@router.get("/health")
async def health_check():
    """系统健康检查"""
    ollama_ok = await check_ollama_health()
    return {
        "status": "ok" if ollama_ok else "degraded",
        "services": {
            "ollama": "ok" if ollama_ok else "unavailable",
            "knowledge_base": "ok",
            "database": "ok"
        },
        "message": "系统正常运行" if ollama_ok else "AI 服务不可用，知识库搜索仍可用"
    }


@router.post("/diagnose")
async def diagnose(request: DiagnoseRequest):
    """故障诊断 - 结合知识库"""
    # 先获取知识库上下文（这个不需要 AI）
    knowledge_context = get_knowledge_context(request.symptom)
    
    # 构建提示词
    prompt = f"""你是一位资深的 PLC 自动化工程师。请根据以下信息进行故障诊断。

## 故障现象
{request.symptom}

## 额外上下文
{request.context or '无'}
{knowledge_context}
---

请分析可能的故障原因，并给出排查建议。
简洁回复，包含：可能原因（按可能性排序）、排查步骤、预防措施。"""

    # 调用 AI
    success, result = await call_ollama(prompt, request.model)
    
    if not success:
        # AI 不可用时，返回知识库结果
        return {
            "symptom": request.symptom,
            "analysis": None,
            "error": result,
            "knowledge_context": knowledge_context,
            "model": request.model,
            "knowledge_used": bool(knowledge_context),
            "ai_available": False
        }
    
    return {
        "symptom": request.symptom,
        "analysis": result,
        "model": request.model,
        "knowledge_used": bool(knowledge_context),
        "ai_available": True
    }


@router.post("/chat")
async def chat(request: ChatRequest):
    """智能对话 - 结合知识库回答问题"""
    # 获取知识库上下文
    knowledge_context = get_knowledge_context(request.message)
    
    # 构建提示词
    prompt = f"""你是 PLC 智能控制系统的 AI 助手。

## 用户问题
{request.message}

## 额外上下文
{request.context or '无'}
{knowledge_context}
---

请给出专业、准确的回答。简洁明了。"""

    # 调用 AI
    success, result = await call_ollama(prompt, request.model)
    
    if not success:
        return {
            "message": request.message,
            "response": None,
            "error": result,
            "knowledge_context": knowledge_context,
            "model": request.model,
            "knowledge_used": bool(knowledge_context),
            "ai_available": False
        }
    
    return {
        "message": request.message,
        "response": result,
        "model": request.model,
        "knowledge_used": bool(knowledge_context),
        "ai_available": True
    }


@router.get("/knowledge")
async def search_knowledge(q: str, limit: int = 5):
    """搜索知识库 - 不需要 AI，总是可用"""
    results = db.search_knowledge(q, limit)
    return {"query": q, "results": results, "count": len(results)}


@router.post("/infer-variables")
async def infer_variable_names(request: VariableInferRequest):
    """
    AI 推断变量名 - 分析 STL 代码逻辑，为变量推断合理的名称
    
    根据代码逻辑、常见 PLC 应用模式，推断每个变量的实际用途并建议变量名
    """
    # 构建变量列表摘要
    var_list = []
    for v in request.variables:
        addr = v.get('address', '')
        dtype = v.get('data_type', '')
        name = v.get('name', '')
        var_list.append(f"  - {addr}: {dtype} (当前名: {name})")
    
    variables_str = "\n".join(var_list)
    
    # 提取关键代码片段（限制长度）
    code_preview = request.code[:2000] if len(request.code) > 2000 else request.code
    
    # 构建 AI 提示词
    prompt = f"""你是西门子 S7-200 SMART PLC 编程专家。请分析以下 STL 代码，推断每个变量的实际用途并给出合理的变量名建议。

## 已识别的变量列表
{variables_str}

## STL 代码片段
```
{code_preview}
```

## 分析要求
1. 根据代码逻辑分析每个变量的用途
2. 常见模式识别：
   - I0.0/I0.1 等输入点通常是按钮、开关、传感器
   - Q0.0 等输出点通常是电机、阀门、指示灯
   - LD + O + AN + = 是典型启停电路（自锁）
   - LDN + S/R 是置位复位电路
   - TON/TOF 是定时器，CTU/CTD 是计数器
3. 变量命名规范：使用有意义的英文名，如 StartButton, MotorOutput, Temperature

## 输出格式
请以 JSON 格式输出，格式如下：
```json
[
  {{"address": "I0.0", "suggested_name": "StartButton", "description": "启动按钮", "confidence": 0.9}},
  {{"address": "I0.1", "suggested_name": "StopButton", "description": "停止按钮", "confidence": 0.9}},
  {{"address": "Q0.0", "suggested_name": "MotorOutput", "description": "电机输出/运行指示", "confidence": 0.85}}
]
```

只输出 JSON 数组，不要其他内容。如果无法推断，confidence 设为 0.3 以下。"""

    # 调用 AI
    success, result = await call_ollama(prompt, request.model)
    
    if not success:
        return {
            "success": False,
            "error": result,
            "variables": request.variables,
            "ai_available": False
        }
    
    # 解析 AI 返回的 JSON
    try:
        # 尝试提取 JSON 内容
        json_str = result.strip()
        # 移除可能的 markdown 代码块标记
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()
        
        suggestions = json.loads(json_str)
        
        # 合并建议到原变量列表
        enhanced_variables = []
        for v in request.variables:
            addr = v.get('address', '')
            # 查找对应的建议
            suggestion = next((s for s in suggestions if s.get('address', '').upper() == addr.upper()), None)
            
            enhanced_var = v.copy()
            if suggestion:
                enhanced_var['suggested_name'] = suggestion.get('suggested_name', '')
                enhanced_var['description'] = suggestion.get('description', '')
                enhanced_var['confidence'] = suggestion.get('confidence', 0)
            else:
                enhanced_var['suggested_name'] = ''
                enhanced_var['description'] = ''
                enhanced_var['confidence'] = 0
            
            enhanced_variables.append(enhanced_var)
        
        return {
            "success": True,
            "variables": enhanced_variables,
            "raw_suggestions": suggestions,
            "model": request.model,
            "ai_available": True
        }
        
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"AI 返回格式解析失败: {str(e)}",
            "raw_response": result,
            "variables": request.variables,
            "ai_available": True
        }
