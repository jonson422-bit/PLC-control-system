"""
告警管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
from database import (
    get_alarm_rules, create_alarm_rule,
    get_active_alarms, create_alarm_event, acknowledge_alarm
)

router = APIRouter()


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
    return {"rules": rules, "count": len(rules)}


@router.post("/rules")
async def create_rule(rule: CreateAlarmRule):
    """创建告警规则"""
    rule_id = create_alarm_rule(rule.model_dump())
    return {"success": True, "rule_id": rule_id, "message": "告警规则创建成功"}


@router.get("")
async def list_alarms(status: str = "active"):
    """获取告警列表"""
    if status == "active":
        alarms = get_active_alarms()
    else:
        # TODO: 实现其他状态查询
        alarms = get_active_alarms()
    return {"alarms": alarms, "count": len(alarms)}


@router.post("/{alarm_id}/acknowledge")
async def ack_alarm(alarm_id: int, user: str = "system"):
    """确认告警"""
    success = acknowledge_alarm(alarm_id, user)
    if success:
        return {"success": True, "message": f"告警 {alarm_id} 已确认"}
    raise HTTPException(status_code=404, detail="告警不存在")
