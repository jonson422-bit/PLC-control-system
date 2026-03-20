"""
PLC 智能管控后端服务 - FastAPI 主程序 (带 WebSocket 实时推送)

改进版本：
1. 结构化日志
2. 后台任务优雅取消
3. WebSocket 超时和心跳机制
4. 全局 HTTP 客户端复用
"""
import sys
sys.path.insert(0, '/home/pi/envs/plc_env/lib/python3.11/site-packages')

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
import httpx
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).parent / ".env")

from .database import init_db, get_db, save_batch_monitor_data, create_alarm_event, get_monitored_addresses, get_monitored_points_config, get_enabled_alarm_rules, create_alarm_log
from .plc_client import PLCClient
from .routes import plc, alarms, ai, points, devices, history, knowledge
from .routes import program_routes
from .logger import get_logger

# 获取日志器
logger = get_logger(__name__)

# ============ 配置常量 ============
# 后台任务间隔配置（秒）
CONNECTION_MONITOR_INTERVAL = int(os.getenv("CONNECTION_MONITOR_INTERVAL", "3"))
DATA_PUSH_INTERVAL = int(os.getenv("DATA_PUSH_INTERVAL", "1"))
ALARM_MONITOR_INTERVAL = int(os.getenv("ALARM_MONITOR_INTERVAL", "2"))
ERROR_RETRY_INTERVAL = int(os.getenv("ERROR_RETRY_INTERVAL", "5"))

# WebSocket 配置
WS_IDLE_TIMEOUT = 120.0  # 空闲超时（秒）
WS_PING_INTERVAL = 30.0  # 心跳间隔（秒）

# 数据保存配置
DATA_SAVE_INTERVAL = int(os.getenv("DATA_SAVE_INTERVAL", "60"))  # 每N次推送保存一次历史数据
# ==================================

# 静态文件目录
STATIC_DIR = Path(__file__).parent / "static"

# 全局 PLC 客户端
plc_client = PLCClient()

# 注入 PLC 客户端到路由模块（避免循环导入）
plc_routes = None
try:
    from .routes import plc as _plc_routes
    _plc_routes.set_plc_client(plc_client)
    plc_routes = _plc_routes
except Exception as e:
    logger.warning(f"注入 PLC 客户端到路由失败: {e}")

# 飞书通知配置 - 从环境变量读取
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_RECEIVE_ID = os.getenv("FEISHU_RECEIVE_ID", "")

# 检查必要配置
if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_RECEIVE_ID]):
    logger.warning("飞书配置不完整，请检查 .env 文件")

# 系统控制标志和状态锁
monitoring_enabled = False  # 监控启用状态（默认关闭，用户需要点击启动按钮）
system_manually_stopped = False  # 系统是否手动停止（控制飞书通知）

# 连接状态追踪
last_connection_state = True  # 上一次的连接状态
connection_alarm_sent = False  # 是否已发送断连告警

# 状态锁 - 保护全局状态的并发访问
_state_lock = asyncio.Lock()

# 全局 HTTP 客户端（复用连接池）
_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """获取全局 HTTP 客户端"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
    return _http_client


async def close_http_client():
    """关闭全局 HTTP 客户端"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._connection_times: dict = {}  # 记录每个连接的建立时间
        self._last_activity: dict = {}  # 记录每个连接的最后活动时间

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        now = datetime.now()
        self._connection_times[websocket] = now
        self._last_activity[websocket] = now
        logger.info(f"WebSocket 连接: {len(self.active_connections)} 个客户端")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        # 清理时间记录
        self._connection_times.pop(websocket, None)
        self._last_activity.pop(websocket, None)
        logger.info(f"WebSocket 断开: {len(self.active_connections)} 个客户端")

    def update_activity(self, websocket: WebSocket):
        """更新连接的活动时间"""
        self._last_activity[websocket] = datetime.now()

    def get_idle_time(self, websocket: WebSocket) -> float:
        """获取连接的空闲时间（秒）"""
        last = self._last_activity.get(websocket)
        if last:
            return (datetime.now() - last).total_seconds()
        return 0

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                self.update_activity(connection)
            except Exception as e:
                # 记录异常并标记连接为断开
                logger.warning(f"WebSocket发送失败: {e}")
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# 飞书 tenant_access_token 缓存
_feishu_token_cache = {"token": None, "expires_at": 0}

async def get_feishu_token():
    """获取飞书 tenant_access_token - 使用全局异步客户端"""
    import time

    # 检查缓存是否有效
    if _feishu_token_cache["token"] and _feishu_token_cache["expires_at"] > time.time():
        return _feishu_token_cache["token"]

    try:
        client = await get_http_client()
        response = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET
            },
            headers={"Content-Type": "application/json"}
        )

        logger.debug(f"飞书API响应: status={response.status_code}")

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                token = data.get("tenant_access_token")
                expire = data.get("expire", 7200)
                _feishu_token_cache["token"] = token
                _feishu_token_cache["expires_at"] = time.time() + expire - 300  # 提前5分钟过期
                logger.info("获取飞书token成功")
                return token
            else:
                logger.warning(f"获取飞书token失败: code={data.get('code')}, msg={data.get('msg')}")
        else:
            logger.warning(f"飞书API请求失败: {response.status_code}, body={response.text[:200]}")
    except httpx.TimeoutException as e:
        logger.warning(f"获取飞书token超时: {e}")
    except httpx.NetworkError as e:
        logger.warning(f"获取飞书token网络错误: {e}")
    except Exception as e:
        logger.error(f"获取飞书token异常: type={type(e).__name__}, msg={e}")

    return None

# 发送飞书通知的异步函数
async def send_feishu_notification(title: str, content: str, severity: str = "info"):
    """通过飞书 API 发送消息通知 - 使用全局异步客户端"""
    try:
        token = await get_feishu_token()
        if not token:
            logger.warning("无法获取飞书token，跳过通知")
            return False

        full_content = f"{title}\n\n{content}\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        payload = {
            "receive_id": FEISHU_RECEIVE_ID,
            "msg_type": "text",
            "content": json.dumps({"text": full_content}, ensure_ascii=False)
        }

        client = await get_http_client()
        response = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                logger.info(f"已发送飞书通知: {title}")
                return True
            else:
                logger.warning(f"飞书消息发送失败: code={data.get('code')}, msg={data.get('msg')}")
        else:
            logger.warning(f"飞书API请求失败: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        logger.error(f"飞书通知异常: type={type(e).__name__}, msg={e}")

    return False

# 通知用户的异步函数（通过飞书）
async def notify_openclaw(event_type: str, data: dict):
    """发送事件通知"""
    try:
        severity = data.get('severity', 'info')
        message = data.get('message', '')
        ip = data.get('ip', '192.168.2.1')

        # 根据事件类型构建消息
        if event_type == 'plc_disconnected':
            title = "PLC 断连告警"
            content = f"PLC 已断开连接！\n\nIP: {ip}\n详情: {message}\n\n请检查网络连接和 PLC 状态。"
            await send_feishu_notification(title, content, "critical")
        elif event_type == 'plc_reconnected':
            title = "PLC 恢复通知"
            content = f"PLC 已重新连接\n\nIP: {ip}\n详情: {message}"
            await send_feishu_notification(title, content, "info")
        elif event_type == 'plc_alarm':
            title = f"PLC 告警：{data.get('rule_name', '未知告警')}"
            content = f"点位: {data.get('point', '-')}\n值: {data.get('value', '-')}\n详情: {message}"
            await send_feishu_notification(title, content, severity)
        else:
            title = f"PLC 系统通知"
            content = f"{event_type}\n\n{message}"
            await send_feishu_notification(title, content, "info")

    except Exception as e:
        logger.error(f"通知异常: {e}")

# 创建 PLC 断连告警
async def create_plc_disconnect_alarm():
    """创建 PLC 断连告警事件"""
    try:
        alarm_id = create_alarm_event({
            'point': 'PLC_CONNECTION',
            'value': 0,
            'message': 'PLC 连接已断开，请检查网络连接和 PLC 状态',
            'severity': 'critical'
        })
        logger.critical(f"已创建 PLC 断连告警: ID={alarm_id}")
        return alarm_id
    except Exception as e:
        logger.error(f"创建告警失败: {e}")
        return None

# 数据存储计数器
save_counter = 0

# 获取已配置的监控变量地址列表
def get_monitored_point_addresses():
    """从数据库获取已配置的监控变量地址列表"""
    try:
        return get_monitored_addresses()
    except Exception as e:
        logger.error(f"获取监控变量失败: {e}")
        return []

# 获取监控变量的完整配置
def get_monitored_points_info():
    """获取监控变量的完整配置（包含地址和名称）"""
    try:
        return get_monitored_points_config()
    except Exception as e:
        logger.error(f"获取监控变量配置失败: {e}")
        return []

# PLC 连接状态监控任务
async def connection_monitor():
    """监控 PLC 连接状态，检测断连并触发告警"""
    global last_connection_state, connection_alarm_sent, monitoring_enabled

    try:
        while True:
            try:
                # 检查监控是否启用
                async with _state_lock:
                    is_monitoring = monitoring_enabled

                if not is_monitoring:
                    # 监控未启用，等待后继续检查
                    await asyncio.sleep(CONNECTION_MONITOR_INTERVAL)
                    continue

                current_state = plc_client.is_connected()

                # 使用锁保护状态读取和更新
                async with _state_lock:
                    prev_state = last_connection_state
                    was_alarm_sent = connection_alarm_sent

                # 检测从连接变为断开
                if prev_state and not current_state:
                    logger.critical("PLC 连接已断开!")

                    # 1. 创建告警事件
                    alarm_id = await create_plc_disconnect_alarm()

                    # 2. 通过 WebSocket 广播给前端
                    await manager.broadcast({
                        "type": "alarm",
                        "timestamp": datetime.now().isoformat(),
                        "data": {
                            "rule_id": None,
                            "rule_name": "PLC连接断开",
                            "point": "PLC_CONNECTION",
                            "value": 0,
                            "message": "PLC 连接已断开，请检查网络连接和 PLC 状态",
                            "severity": "critical",
                            "alarm_id": alarm_id
                        }
                    })

                    # 3. 通知 OpenClaw (仅在非手动停止时)
                    async with _state_lock:
                        should_notify = not system_manually_stopped
                    if should_notify:
                        await notify_openclaw("plc_disconnected", {
                            "ip": plc_client.ip,
                            "message": "PLC 连接已断开",
                            "severity": "critical",
                            "alarm_id": alarm_id
                        })
                    else:
                        logger.info("系统已手动停止，跳过飞书通知")

                    # 更新状态
                    async with _state_lock:
                        connection_alarm_sent = True

                # 检测从断开变为连接
                elif not prev_state and current_state:
                    logger.info("PLC 连接已恢复!")

                    # 通过 WebSocket 广播恢复通知
                    await manager.broadcast({
                        "type": "alarm",
                        "timestamp": datetime.now().isoformat(),
                        "data": {
                            "rule_name": "PLC连接恢复",
                            "point": "PLC_CONNECTION",
                            "value": 1,
                            "message": "PLC 连接已恢复正常",
                            "severity": "info"
                        }
                    })

                    # 通知 OpenClaw
                    await notify_openclaw("plc_reconnected", {
                        "ip": plc_client.ip,
                        "message": "PLC 连接已恢复"
                    })

                    # 更新状态
                    async with _state_lock:
                        system_manually_stopped = False
                        connection_alarm_sent = False

                # 更新连接状态
                async with _state_lock:
                    last_connection_state = current_state

                await asyncio.sleep(CONNECTION_MONITOR_INTERVAL)

            except asyncio.CancelledError:
                logger.info("connection_monitor 任务被取消，正在退出...")
                raise
            except Exception as e:
                logger.error(f"连接监控错误: {e}")
                await asyncio.sleep(ERROR_RETRY_INTERVAL)
    except asyncio.CancelledError:
        logger.info("connection_monitor 已停止")

# 后台数据推送任务
async def data_pusher():
    """定时推送 PLC 数据到所有 WebSocket 客户端"""
    global save_counter
    try:
        while True:
            try:
                connected = plc_client.is_connected()
                if manager.active_connections:
                    if connected:
                        # 获取监控变量的完整配置
                        monitor_config = get_monitored_points_info()

                        if not monitor_config:
                            await asyncio.sleep(1)
                            continue

                        # 提取地址列表
                        point_addresses = [cfg['address'] for cfg in monitor_config if cfg.get('address')]

                        if not point_addresses:
                            await asyncio.sleep(1)
                            continue

                        # 读取配置的点位数据
                        data = plc_client.read_points(point_addresses)
                        if data:
                            # 构建地址到配置的映射
                            address_to_config = {cfg['address']: cfg for cfg in monitor_config}

                            # 构建带配置信息的数据列表
                            data_list = []
                            for point_name, point_data in data.get('points', {}).items():
                                if point_data.get('success'):
                                    cfg = address_to_config.get(point_name, {})
                                    data_list.append({
                                        'address': point_name,
                                        'name': cfg.get('name', point_name),
                                        'value': point_data.get('value'),
                                        'raw_value': point_data.get('raw_value'),
                                        'type': point_data.get('type'),
                                        'category': cfg.get('category', 'input'),
                                        'unit': cfg.get('unit', ''),
                                        'description': cfg.get('description', ''),
                                        'data_type': cfg.get('data_type', 'bit')
                                    })

                            message = {
                                "type": "plc_data",
                                "timestamp": datetime.now().isoformat(),
                                "data": data_list,
                                "monitor_config": monitor_config,
                                "monitored_count": len(point_addresses)
                            }
                            await manager.broadcast(message)

                            # 每10秒存储一次历史数据
                            save_counter += 1
                            if save_counter >= 10:
                                save_counter = 0
                                try:
                                    history_data = []
                                    for item in data_list:
                                        history_data.append({
                                            'point': item['address'],
                                            'value': item.get('raw_value', 0),
                                            'raw_value': item.get('raw_value', 0),
                                            'quality': 'good'
                                        })
                                    if history_data:
                                        save_batch_monitor_data(history_data)
                                except Exception as e:
                                    logger.error(f"历史数据存储错误: {e}")
                    else:
                        # 广播断连状态
                        await manager.broadcast({
                            "type": "plc_disconnected",
                            "timestamp": datetime.now().isoformat()
                        })
                await asyncio.sleep(DATA_PUSH_INTERVAL)
            except asyncio.CancelledError:
                logger.info("data_pusher 任务被取消，正在退出...")
                raise
            except Exception as e:
                logger.error(f"数据推送错误: {e}")
                await asyncio.sleep(ERROR_RETRY_INTERVAL)
    except asyncio.CancelledError:
        logger.info("data_pusher 已停止")

# 后台告警监控任务
async def alarm_monitor():
    """定时检查告警规则"""
    last_trigger_time = {}  # 记录每个规则的最后触发时间

    try:
        while True:
            try:
                if plc_client.is_connected():
                    rules = get_enabled_alarm_rules()
                    for rule in rules:
                        # 读取点位值
                        value = plc_client.read_point(rule['point'])
                        if value is not None:
                            # 检查条件
                            triggered = False
                            threshold = rule['threshold']
                            operator = rule['operator']

                            if operator == ">" and value > threshold:
                                triggered = True
                            elif operator == "<" and value < threshold:
                                triggered = True
                            elif operator == ">=" and value >= threshold:
                                triggered = True
                            elif operator == "<=" and value <= threshold:
                                triggered = True
                            elif operator == "==" and value == threshold:
                                triggered = True
                            elif operator == "!=" and value != threshold:
                                triggered = True

                            if triggered:
                                # 检查冷却时间
                                last_time = last_trigger_time.get(rule['id'])
                                cooldown = timedelta(seconds=rule.get('cooldown_seconds') or 60)

                                if last_time is None or datetime.now() - last_time > cooldown:
                                    # 创建告警日志
                                    create_alarm_log(
                                        rule_id=rule['id'],
                                        point=rule['point'],
                                        value=value,
                                        message=rule['message'],
                                        severity=rule['severity']
                                    )

                                    # 推送告警到 WebSocket
                                    await manager.broadcast({
                                        "type": "alarm",
                                        "timestamp": datetime.now().isoformat(),
                                        "data": {
                                            "rule_id": rule['id'],
                                            "rule_name": rule['name'],
                                            "point": rule['point'],
                                            "value": value,
                                            "message": rule['message'],
                                            "severity": rule['severity']
                                        }
                                    })

                                    last_trigger_time[rule['id']] = datetime.now()
                                    logger.warning(f"告警触发: {rule['name']} - {rule['message']}")
                await asyncio.sleep(ALARM_MONITOR_INTERVAL)
            except asyncio.CancelledError:
                logger.info("alarm_monitor 任务被取消，正在退出...")
                raise
            except Exception as e:
                logger.error(f"告警监控错误: {e}")
                await asyncio.sleep(ERROR_RETRY_INTERVAL)
    except asyncio.CancelledError:
        logger.info("alarm_monitor 已停止")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    init_db()
    logger.info("PLC Control Service starting...")
    logger.info("Database initialized")

    # 启动后台任务
    background_tasks = [
        asyncio.create_task(data_pusher()),
        asyncio.create_task(alarm_monitor()),
        asyncio.create_task(connection_monitor())
    ]
    logger.info("后台任务已启动")

    yield

    # 关闭时优雅清理
    logger.info("正在停止后台任务...")
    for task in background_tasks:
        task.cancel()

    # 等待所有任务完成取消
    await asyncio.gather(*background_tasks, return_exceptions=True)

    # 关闭 HTTP 客户端
    await close_http_client()

    # 清理其他资源
    plc_client.disconnect()
    logger.info("PLC Control Service stopped")

app = FastAPI(
    title="PLC Control API",
    description="PLC智能管控系统后端API",
    version="1.2.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(plc.router, prefix="/api/plc", tags=["PLC"])
app.include_router(alarms.router, prefix="/api/alarms", tags=["Alarms"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(points.router, prefix="/api/points", tags=["Points"])
app.include_router(devices.router, prefix="/api/devices", tags=["Devices"])
app.include_router(history.router, prefix="/api/data", tags=["History"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(program_routes.router, prefix="/api/programs", tags=["Program"])


@app.get("/")
async def root():
    """返回 Dashboard 页面"""
    dashboard = STATIC_DIR / "dashboard.html"
    if dashboard.exists():
        return FileResponse(dashboard)
    return {"message": "PLC Control API", "version": "1.2.0"}


@app.get("/api")
async def api_info():
    """API 信息"""
    return {"message": "PLC Control API", "version": "1.2.0", "websocket": "/ws"}


@app.get("/health")
async def health():
    """使用缓存的连接状态，避免阻塞"""
    return {"status": "healthy", "plc_connected": plc_client._connected}


@app.post("/api/test/feishu")
async def test_feishu_notification():
    """测试飞书通知"""
    result = await send_feishu_notification(
        "测试通知",
        "这是一条来自 PLC 控制系统的测试消息，用于验证飞书通知功能是否正常工作。"
    )
    return {"success": result, "message": "飞书通知已发送" if result else "飞书通知发送失败"}


@app.post("/api/system/stop")
async def system_stop():
    """标记系统手动停止，禁用飞书通知"""
    global system_manually_stopped
    async with _state_lock:
        system_manually_stopped = True
    logger.info("系统已手动停止，禁用断连飞书通知")
    return {"success": True, "message": "系统已停止，不会发送断连通知"}


@app.post("/api/system/start")
async def system_start():
    """标记系统启动，恢复飞书通知"""
    global system_manually_stopped
    async with _state_lock:
        system_manually_stopped = False
    logger.info("系统已启动，恢复断连飞书通知")
    return {"success": True, "message": "系统已启动"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时数据推送端点 - 带超时和心跳检测"""
    await manager.connect(websocket)

    # 心跳任务
    async def heartbeat():
        """定期发送心跳检测"""
        while True:
            try:
                await asyncio.sleep(WS_PING_INTERVAL)
                # 检查空闲时间
                idle_time = manager.get_idle_time(websocket)
                if idle_time > WS_IDLE_TIMEOUT:
                    logger.warning(f"WebSocket 连接空闲超时 ({idle_time:.0f}s)，正在断开")
                    await websocket.close(code=1001, reason="Idle timeout")
                    return
                # 发送心跳
                await websocket.send_json({"type": "ping"})
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug(f"心跳任务异常: {e}")
                return

    # 启动心跳任务
    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            try:
                # 等待客户端消息，带超时
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_IDLE_TIMEOUT
                )
                manager.update_activity(websocket)

                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg.get("type") == "pong":
                        # 收到心跳响应，连接正常
                        pass
                except json.JSONDecodeError as e:
                    logger.warning(f"WebSocket消息解析失败: {e}")

            except asyncio.TimeoutError:
                logger.warning("WebSocket 接收超时，正在断开")
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket 客户端主动断开")
    except Exception as e:
        logger.error(f"WebSocket连接异常: {e}")
    finally:
        # 取消心跳任务
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(websocket)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("PLC Control Service")
    logger.info("API: http://localhost:8088")
    logger.info("Dashboard: http://localhost:8088")
    logger.info("WebSocket: ws://localhost:8088/ws")
    logger.info("Docs: http://localhost:8088/docs")
    logger.info("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8088)
