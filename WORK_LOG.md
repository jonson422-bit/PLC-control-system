# PLC 智能管控系统 - 工作日志

## 2025-03-17

### 完成的工作

#### 1. PLC 连接状态检测修复
- **问题**: `is_connected()` 方法只检查 socket 端口和 client 对象，没有真正验证 PLC 连接有效性
- **文件**: `/home/pi/plc-control-system/backend/plc_service/plc_client.py`
- **修复**: 修改 `is_connected()` 方法，调用 `_check_connection()` 通过 `get_cpu_state()` 验证连接

#### 2. WebSocket 状态广播优化
- **问题**: 断开连接时不主动广播状态给前端
- **文件**: `/home/pi/plc-control-system/backend/plc_service/main.py`
- **修复**: `data_pusher()` 在连接断开时广播 `plc_disconnected` 消息

#### 3. 前端状态显示修复
- **问题**: 前端收到告警消息时只显示 toast，不更新状态指示器
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **修复**: 处理 `PLC_CONNECTION` 告警消息，更新连接状态显示

#### 4. 飞书通知功能修复
- **问题**: `httpx.AsyncClient` 在 FastAPI 异步环境中存在兼容性问题，导致获取 token 和发送消息失败
- **文件**: `/home/pi/plc-control-system/backend/plc_service/main.py`
- **修复**: 
  - `get_feishu_token()`: 使用 `asyncio.to_thread()` 包装同步的 `httpx.Client`
  - `send_feishu_notification()`: 同样改用同步方式
- **结果**: PLC 断开/恢复连接时自动发送飞书通知

#### 5. STL 解析器增强（之前完成）
- 添加 STL_INSTRUCTIONS 字典识别各种指令
- 添加地址验证过滤无效变量
- 修复 END_VAR 被误认为代码块结束的问题

#### 6. 程序管理功能（之前完成）
- 添加程序删除功能
- 修复程序列表显示

#### 7. Dashboard 前端修复
- **问题**: `dashboard.html` 缺少 `<script>` 标签，JavaScript 代码直接暴露导致乱码
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **修复**: 添加 `<script>` 标签包裹 JavaScript 代码

#### 8. 前端 API_URL 跨域修复
- **问题**: `API_URL` 硬编码为 `http://localhost:8088`，通过其他 IP 访问时跨域失败
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **修复**: 改为 `window.location.origin`，自动使用当前访问地址

#### 9. API 响应性能优化（重要）
- **问题**: 所有 API 响应极慢（设备列表 26 秒，添加设备 8 秒）
- **原因**: `is_connected()` 方法在 PLC 不可达时执行 socket 连接测试（超时 1-2 秒），阻塞 FastAPI 事件循环
- **修复**:
  - `/home/pi/plc-control-system/backend/plc_service/main.py`: `/health` 端点使用缓存状态 `plc_client._connected`
  - `/home/pi/plc-control-system/backend/plc_service/routes/plc.py`: 所有端点使用缓存状态代替实时检测
  - `/home/pi/plc-control-system/backend/plc_service/routes/devices.py`: 数据库操作使用 `asyncio.to_thread` 包装
- **结果**: 设备列表 0.022 秒，添加设备 0.045 秒（性能提升 500+ 倍）

#### 10. 数据库初始化修复
- **问题**: 每次启动尝试插入默认点位，遇到 UNIQUE 约束冲突导致启动失败
- **文件**: `/home/pi/plc-control-system/backend/plc_service/database.py`
- **修复**: `INSERT` 改为 `INSERT OR IGNORE`

#### 11. 知识库管理前端功能（新增）
- **需求**: 前端缺失"知识库管理"功能模块
- **后端 API**: `/api/knowledge/*` 已存在（列表、分类、增删改查、搜索、文件导入）
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **新增功能**:
  - 知识库管理标签页（导航栏新增"知识库"入口）
  - 知识列表展示（分类标签、标题、内容预览、关键词、关联点位）
  - 分类筛选下拉框
  - 实时搜索功能
  - 添加/编辑知识模态框
  - 删除知识功能
  - 查看知识详情
  - 文件上传导入（支持 JSON/Markdown 格式）
- **后端 API 端点**:
  - `GET /api/knowledge/list` - 获取知识列表（支持 ?category= 筛选）
  - `GET /api/knowledge/categories` - 获取所有分类
  - `GET /api/knowledge/{id}` - 获取单条知识详情
  - `POST /api/knowledge/add` - 添加知识
  - `PUT /api/knowledge/{id}` - 更新知识
  - `DELETE /api/knowledge/{id}` - 删除知识
  - `GET /api/knowledge/search/{query}` - 搜索知识
  - `POST /api/knowledge/upload` - 上传文件导入

#### 12. 前端 WebSocket 实时更新功能（新增）
- **需求**: 前端使用 HTTP 轮询获取数据，效率低且无法接收实时告警
- **后端**: WebSocket 端点 `/ws` 已实现，支持 PLC 数据推送、告警推送、心跳机制
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **改动**:
  - 移除 HTTP 轮询 (`setInterval(fetchData, 1000)`)
  - 新增 WebSocket 连接管理函数 `connectWebSocket()`
  - 新增消息处理函数 `handleMessage()` 处理 `plc_data`、`alarm`、`pong` 消息
  - 新增心跳机制 (30秒间隔发送 `ping`)
  - 新增断线自动重连 (3秒后重连)
  - 新增 Toast 通知显示告警消息
- **优点**:
  - 减少服务器负载（无需每秒 HTTP 请求）
  - 实时接收告警通知
  - 更快的响应速度
  - 自动重连保证稳定性

#### 13. 点位管理前端功能（新增）
- **需求**: 前端"点位配置"标签页缺少交互功能
- **后端 API**: `/api/points/*` 已存在，但缺少增删改端点
- **文件**: 
  - `/home/pi/plc-control-system/backend/plc_service/routes/points.py` - 后端路由
  - `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html` - 前端页面
- **后端新增 API**:
  - `POST /api/points` - 创建点位
  - `PUT /api/points/{id}` - 更新点位
  - `DELETE /api/points/{id}` - 删除点位
  - `GET /api/points/name/{name}` - 通过名称获取点位
- **前端新增功能**:
  - `showTab()` 函数添加 `points` 标签处理，调用 `loadPoints()`
  - 点位编辑模态框（地址、名称、分类、数据类型、单位、缩放、范围、备注、启用/历史记录）
  - `loadPoints()` - 加载点位列表，支持分类筛选
  - `showPointModal()` / `closePointModal()` - 显示/关闭模态框
  - `savePoint()` - 保存点位（新增/编辑）
  - `editPoint()` - 编辑点位
  - `deletePoint()` - 删除点位
- **点位分类颜色**:
  - 数字量输入: #00d9ff (蓝)
  - 数字量输出: #00ff88 (绿)
  - 模拟量输入: #ffc107 (黄)
  - 模拟量输出: #ff6b6b (红)
  - 内存区: #a55eea (紫)
- **问题修复**: 后端服务重启后 DELETE API 正常工作

#### 14. 告警规则管理前端功能（新增）
- **需求**: 前端缺失"告警规则创建"功能模块
- **后端 API**: `/api/alarms/rules/*` 已存在
- **文件**:
  - `/home/pi/plc-control-system/backend/plc_service/routes/alarms.py` - 后端路由
  - `/home/pi/plc-control-system/backend/plc_service/database.py` - 数据库函数
  - `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html` - 前端页面
- **后端新增 API**:
  - `GET /api/alarms/rules/{id}` - 获取单个规则
  - `PUT /api/alarms/rules/{id}` - 更新规则
  - `DELETE /api/alarms/rules/{id}` - 删除规则
- **前端新增功能**:
  - 告警规则列表展示（显示规则名称、监控点位、条件、阈值、严重程度、状态）
  - 告警规则创建/编辑模态框
  - `loadAlarmRules()` - 加载告警规则列表
  - `showAlarmRuleModal()` / `closeAlarmRuleModal()` - 显示/关闭模态框
  - `saveAlarmRule()` - 保存告警规则
  - `editAlarmRule()` - 编辑告警规则
  - `deleteAlarmRule()` - 删除告警规则
- **showTab() 函数**: 添加 `loadAlarmRules()` 调用

#### 15. 程序上传变量解析Bug修复
- **问题**: 上传PLC程序后，变量列表为空（variable_count=0）
- **原因**: `program_routes.py` 变量提取逻辑错误
  - 错误代码: `for block in result.get('blocks', []): for var in block.get('variables', [])`
  - STL解析器返回的变量在 `result['variables']` 中，而非 `blocks` 的 `variables` 字段
- **文件**: `/home/pi/plc-control-system/backend/plc_service/routes/program_routes.py`
- **修复**: 将变量提取改为 `for var in result.get('variables', [])`
- **测试结果**: 上传"冲压机模拟(Press_Test).awl"后正确解析出27个变量
  - BOOL类型: I0.0-I0.7, Q0.0-Q0.4, M0.1-M0.6, M1.0-M1.2
  - WORD类型: VW0
  - TIMER类型: T37, T38, T39, T40

### 飞书通知配置
```python
FEISHU_APP_ID = "cli_a92aea1a6078dbd9"
FEISHU_APP_SECRET = "qY45lm03uygEStes3Dum0no8o5jjAmdu"
FEISHU_RECEIVE_ID = "ou_a53b3daf1230d6e1c62c3fd411414655"  # open_id
```

### 测试 API
- `POST /api/test/feishu` - 测试飞书通知功能

---

## 2025-03-18

### 完成的工作

#### 1. 变量管理功能整合
- **需求**: 将分散的"程序管理"和"点位配置"整合为统一的"变量管理"功能
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **改动**:
  - 导航栏合并为6个标签：实时监控、输出控制、变量管理、告警管理、设备管理、知识诊断
  - 变量管理整合：程序上传、STL解析、变量列表、导入点位配置
  - 变量列表支持筛选（按分类、导入状态）
  - 支持单选/全选批量导入变量到点位表
  - 已导入变量可编辑点位配置

#### 2. 变量点位删除功能
- **需求**: 变量列表缺少删除点位按钮
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **新增功能**:
  - 已导入变量显示"编辑"和"删除"两个按钮
  - `deleteVariablePoint()` 函数：删除点位并刷新变量列表
  - 删除确认对话框防止误操作

#### 3. 点位编辑保存修复
- **问题**: 点位编辑保存后，变量列表不显示更新后的数据
- **原因**: 
  - 前端发送字段与后端期望字段不匹配
  - `get_program_variables()` 返回的是JSON文件静态数据，而非数据库最新值
- **文件**: 
  - `/home/pi/plc-control-system/backend/plc_service/routes/points.py`
  - `/home/pi/plc-control-system/backend/plc_service/routes/program_routes.py`
  - `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **修复**:
  - 后端 `PointConfig`/`PointUpdate` 模型添加 `scale`, `min_value`, `max_value`, `log_history` 字段
  - 前端 `savePoint()` 简化发送字段，匹配数据库结构
  - `get_program_variables()` 查询数据库获取点位最新名称和描述
  - 修复 `_check_point_status()` 函数缩进错误

#### 4. 知识库与AI诊断界面合并
- **需求**: Dashboard界面优化，减少标签数量
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **改动**:
  - 导航栏合并"知识库"和"AI诊断"为"知识诊断"
  - 知识诊断页面分为左右两栏布局
  - 左侧：知识库管理（列表、搜索、添加、编辑、删除）
  - 右侧：AI故障诊断（故障描述、开始诊断、结果展示）
  - AI诊断自动搜索知识库相关知识辅助诊断

#### 5. 后端代码语法修复
- **问题**: `program_routes.py` 中 `_check_point_status()` 函数缩进错误
- **原因**: `return variables` 语句缩进在 `with` 块内部，导致 `result = await run_db()` 在异步函数外部
- **修复**: 调整缩进，确保 `return variables` 在 `_check_point_status()` 函数级别

### 服务状态
- 服务运行在: http://192.168.1.16:8088
- 进程: uvicorn main:app --host 0.0.0.0 --port 8088

### 待办事项
- [ ] 其他功能需求待定

---

## 2026-03-18

### 完成的工作

#### 1. 实时监控功能修复
- **问题**: 实时监控显示的参数与变量管理配置不一致
- **原因**:
  - 后端 `data_pusher()` 从 `monitored_variables` 表获取监控变量（旧程序变量表）
  - 前端从 `monitor_config` 表获取配置（点位配置表）
  - 两套配置数据源不同导致不一致
- **修复**:
  - `/home/pi/plc-control-system/backend/plc_service/database.py`: 修改 `get_monitored_addresses()` 从 `monitor_config` 表获取地址
  - 新增 `get_monitored_points_config()` 函数返回完整配置信息
  - `/home/pi/plc-control-system/backend/plc_service/main.py`: 修改 `data_pusher()` 返回带配置信息的数据
  - `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`: 前端正确处理带配置的数据

#### 2. 地址格式统一修复
- **问题**: 点位地址格式不一致
  - 默认点位使用 snap7 格式：`PA:0:0`, `PE:0:0`
  - 导入变量使用 PLC 格式：`I0.6`, `M1.0`
- **修复**:
  - `/home/pi/plc-control-system/backend/plc_service/plc_client.py`: 新增 `_parse_address()` 函数
  - 支持多种地址格式：PLC 格式 (I0.0, Q0.0, M1.0, AIW16) 和 snap7 格式 (PE:0:0, PA:0:0, MK:1:0)
  - 自动识别位地址和字地址

#### 3. 数据库迁移脚本增强
- **文件**: `/home/pi/plc-control-system/backend/plc_service/migrate_db.py`
- **新增**:
  - `points` 表添加 `scale`, `min_value`, `max_value`, `log_history` 字段
  - `system_config` 系统配置表
  - `operation_logs` 操作日志表

---

## 2026-03-18 (续)

### 完成的工作

#### 4. PLC 变量监控功能完善
- **需求**: 实时监控页面只显示分类标题，没有显示变量数据
- **原因分析**:
  - PLC 未连接时，WebSocket 不推送数据，前端无内容显示
  - 变量管理中勾选的"监控"变量需要保存到数据库并读取
- **文件**:
  - `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html` - 前端页面
  - `/home/pi/plc-control-system/backend/plc_service/database.py` - 数据库操作
  - `/home/pi/plc-control-system/backend/plc_service/main.py` - 后端推送逻辑
- **改动**:
  1. **前端实时监控页面结构调整**:
     - 新增"内存变量 (M)"分组区域
     - 分类：数字量输入(I)、数字量输出(Q)、内存变量(M)、模拟量输入(AIW)
  2. **新增 `plc_disconnected` 消息处理**:
     - `handleMessage()` 添加 `case 'plc_disconnected'` 分支
     - PLC 断开时仍显示已配置的监控变量（灰显状态）
  3. **新增 `updateDisconnectedMonitor()` 函数**:
     - PLC 断开时渲染监控变量列表（无值状态）
     - 显示变量名称，值显示"--"，提示"PLC 未连接"
  4. **优化 `loadMonitorPointsConfig()` 函数**:
     - 加载监控配置后检查 PLC 连接状态
     - 若 PLC 未连接，自动调用 `updateDisconnectedMonitor()`
  5. **优化变量分组逻辑**:
     - `updateDynamicMonitor()` 修正分类判断逻辑
     - 优先使用数据库 `category` 字段，其次根据地址前缀判断

#### 5. 实时监控前端性能优化
- **问题**: 实时监控页面反应慢
- **原因**:
  - 使用 `innerHTML +=` 导致多次 DOM 重排
  - 每次刷新都重建整个 DOM 树，即使数据未变化
- **文件**: `/home/pi/plc-control-system/backend/plc_service/static/dashboard.html`
- **优化措施**:
  1. **增量更新机制**:
     - 添加 `lastPointsData` 缓存上次数据
     - 只有变量列表变化时才重建 DOM
     - 数据不变时只更新值元素
  2. **使用 DocumentFragment**:
     - 将多次 DOM 操作合并为一次
     - 减少页面重排次数
  3. **分离创建和更新逻辑**:
     - `createPointElement()`: 创建新 DOM 元素
     - `updatePointElement()`: 只更新变化的值
     - `renderPointsList()`: 统一渲染入口，判断是否需要重建
     - `renderDisconnectedList()`: 断开状态渲染
  4. **使用 `dataset.key` 标识元素**:
     - 快速定位需要更新的元素
     - 避免遍历整个 DOM 树
- **结果**: 
  - 首次渲染：创建 DOM 树
  - 后续刷新：仅更新变化的值（O(1) 操作）
  - 大幅减少页面重排和重绘

### 业务流程说明
1. 用户在"变量管理"页面上传 PLC 程序文件 (.stl/.awl)
2. 系统自动解析程序中的变量点位（I/Q/M/T/C/AI/AQ 等）
3. 用户在变量列表中勾选需要监控的变量（点击"导入"后可勾选"监控"）
4. 监控状态保存到 `monitor_config` 表
5. 实时监控页面读取 `monitor_config` 中的变量配置
6. 若 PLC 连接，从 PLC 读取实时值并显示
7. 若 PLC 断开，显示变量列表但值显示"--"

---
*日志最后更新: 2026-03-18*
