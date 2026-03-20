"""
告警管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
from ..database import (
    get_alarm_rules, create_alarm_rule, get_alarm_rule_by_id,
    update_alarm_rule, delete_alarm_rule,
    get_active_alarms, get_alarms_by_status,
    create_alarm_event, acknowledge_alarm
)
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


class AlarmCondition(BaseModel):
    operator: Literal[">", "<", ">=", "<=", "==", "!="]
    value: float


class CreateAlarmRule(BaseModel):
    name: str
    point: str
    condition: AlarmCondition
    severity: Optional[str] = "warning"
    message: Optional[str] = None
    cooldown_seconds: Optional[int] = 60


@router.get("/rules")
async def list_rules():
    """获取告警规则列表"""
    rules = get_alarm_rules()
    for rule in rules:
        rule['condition'] = {
            'operator': rule.pop('operator'),
            'value': rule.pop('threshold')
        }
    return {"rules": rules, "count": len(rules)}


@router.post("/rules")
async def create_rule(rule: CreateAlarmRule):
    """创建告警规则"""
    rule_id = create_alarm_rule(rule.model_dump())
    return {"success": True, "rule_id": rule_id, "message": "告警规则创建成功"}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: int):
    """获取单个告警规则"""
    rule = get_alarm_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule['condition'] = {
        'operator': rule.pop('operator'),
        'value': rule.pop('threshold')
    }
    return rule


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: int, rule: CreateAlarmRule):
    """更新告警规则"""
    existing = get_alarm_rule_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="规则不存在")
    update_alarm_rule(rule_id, rule.model_dump())
    return {"success": True, "message": "告警规则更新成功"}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    """删除告警规则"""
    existing = get_alarm_rule_by_id(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="规则不存在")
    delete_alarm_rule(rule_id)
    return {"success": True, "message": "告警规则已删除"}


@router.get("")
async def list_alarms(status: str = "active"):
    """获取告警列表"""
    if status in ("active", "acknowledged", "all"):
        alarms = get_alarms_by_status(status)
    else:
        alarms = get_alarms_by_status("active")
    return {"alarms": alarms, "count": len(alarms)}


@router.post("/{alarm_id}/acknowledge")
async def ack_alarm(alarm_id: int, user: str = "system"):
    """确认告警"""
    success = acknowledge_alarm(alarm_id, user)
    if success:
        return {"success": True, "message": f"告警 {alarm_id} 已确认"}
    raise HTTPException(status_code=404, detail="告警不存在")
