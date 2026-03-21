# PLC 智能管控系统

基于 FastAPI 的 S7-200 SMART PLC 智能管控系统，支持实时监控、告警管理、AI故障诊断和知识库管理。

## 功能特性

### 核心功能
- **实时监控**: 读取数字量 I/O 和模拟量 I/O（只读模式，保护设备安全）
- **告警管理**: 创建告警规则，支持多种操作符（>, <, >=, <=, ==, !=）
- **AI 诊断**: 基于 Ollama 的故障智能诊断
- **知识库**: 设备知识管理，支持分类、搜索
- **程序管理**: STL 程序上传、解析和变量提取
- **历史数据**: 数据记录、图表展示和统计分析

### 安全特性
- 只读模式保护设备安全（写入功能已移除）
- 敏感信息通过环境变量管理
- 完善的异常处理和日志记录

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Web Dashboard  │     │  FastAPI 后端   │     │  S7-200 SMART   │
│  (Vue.js)       │────▶│  Python 服务    │────▶│  PLC            │
│  端口 8088      │     │  端口 8088      │     │  192.168.2.1    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Ollama AI      │
                        │  端口 11434     │
                        └─────────────────┘
```

## 快速启动

### 1. 环境准备

```bash
# 激活虚拟环境
source /home/pi/envs/plc_env/bin/activate

# 安装依赖
pip install fastapi uvicorn httpx python-snap7 python-dotenv
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp backend/plc_service/.env.example backend/plc_service/.env

# 编辑配置文件
nano backend/plc_service/.env
```

配置示例：
```
# 飞书应用配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_RECEIVE_ID=your_receive_id

# 后台任务间隔配置（秒）
CONNECTION_MONITOR_INTERVAL=3
DATA_PUSH_INTERVAL=1
ALARM_MONITOR_INTERVAL=2
```

### 3. 启动服务

```bash
cd /home/pi/plc-control-system/backend/plc_service
python main.py
```

### 4. 访问系统

- **Dashboard**: http://192.168.1.16:8088
- **API文档**: http://192.168.1.16:8088/docs

## API 端点

### PLC 操作
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/plc/read` | GET | 读取所有点位 |
| `/api/plc/read/{point}` | GET | 读取单个点位 |
| `/api/plc/status` | GET | 获取连接状态 |
| `/api/plc/cpu` | GET | 获取CPU状态 |

### 告警管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/alarms` | GET | 获取告警列表 |
| `/api/alarms/rules` | GET | 获取告警规则 |
| `/api/alarms/rules` | POST | 创建告警规则 |

### 点位管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/points` | GET | 获取点位列表 |
| `/api/points/{id}` | GET | 获取点位详情 |
| `/api/points/monitor/list` | GET | 获取监控点位 |

### 历史数据
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/data/point/{point}` | GET | 获取点位历史数据 |
| `/api/data/batch` | GET | 批量获取历史数据 |
| `/api/data/statistics/{point}` | GET | 获取统计信息 |

### AI 诊断
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/ai/diagnose` | POST | AI故障诊断 |
| `/api/ai/analyze` | GET | 数据分析 |
| `/api/ai/recommend` | POST | 优化建议 |

### 知识库
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/knowledge/list` | GET | 获取知识列表 |
| `/api/knowledge/categories` | GET | 获取分类列表 |

### 程序管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/programs` | GET | 获取程序列表 |
| `/api/programs/upload` | POST | 上传程序文件 |

## 支持的点位

### 数字量输入 (I0.0 - I0.7)
PLC 输入状态监控

### 数字量输出 (Q0.0 - Q0.7)
输出状态监控（只读）

### 模拟量输入 (AIW16-22)
EM AT04 模块，4路热电偶温度传感器

### 模拟量输出 (AQW32-34)
EM AQ02 模块，2路模拟量输出（只读）

## 目录结构

```
plc-control-system/
├── README.md                   # 项目说明
├── WORK_LOG.md                 # 工作日志
├── .gitignore                  # Git忽略配置
└── backend/
    └── plc_service/
        ├── main.py             # FastAPI 主程序
        ├── database.py         # 数据库操作
        ├── plc_client.py       # PLC 通信客户端
        ├── stl_parser.py       # STL 解析器
        ├── migrate_db.py       # 数据库迁移
        ├── .env.example        # 环境变量模板
        ├── routes/             # API 路由
        │   ├── plc.py          # PLC 操作
        │   ├── alarms.py       # 告警管理
        │   ├── points.py       # 点位管理
        │   ├── history.py      # 历史数据
        │   ├── knowledge.py    # 知识库
        │   ├── program_routes.py # 程序管理
        │   └── ai.py           # AI 诊断
        ├── uploads/            # 上传文件目录
        │   ├── programs/       # 程序文件
        │   └── knowledge/      # 知识库文件
        └── static/
            └── dashboard.html  # Web Dashboard
```

## 配置说明

### 后台任务间隔

可通过环境变量调整后台任务运行间隔：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CONNECTION_MONITOR_INTERVAL` | 3秒 | 连接状态检查间隔 |
| `DATA_PUSH_INTERVAL` | 1秒 | 数据推送间隔 |
| `ALARM_MONITOR_INTERVAL` | 2秒 | 告警检查间隔 |
| `ERROR_RETRY_INTERVAL` | 5秒 | 错误重试间隔 |

### 告警操作符

支持以下比较操作符：
- `>` 大于
- `<` 小于
- `>=` 大于等于
- `<=` 小于等于
- `==` 等于
- `!=` 不等于

## 依赖

- Python 3.11+
- FastAPI
- uvicorn
- httpx
- python-snap7
- python-dotenv
- Ollama (本地运行)

## 故障排除

### PLC 连接失败
1. 检查 PLC IP 地址是否正确
2. 确认网络连通性: `ping 192.168.2.1`
3. 检查 snap7 库是否正确安装

### AI 诊断不可用
1. 确认 Ollama 服务运行: `systemctl status ollama`
2. 检查模型是否已下载: `ollama list`

### 数据库问题
```bash
# 检查数据库文件
ls -la backend/plc_service/plc_control.db

# 运行迁移脚本
python backend/plc_service/migrate_db.py
```

## 版本历史

### v1.2.0 (2026-03-21)
- **安全**: Bearer Token 认证、CORS 配置化
- **稳定性**: 事件循环修复、DATA_SAVE_INTERVAL 配置生效、历史数据自动清理
- **运维**: systemd 服务化（自动重启、开机自启）
- **数据**: CSV 导出、工程量换算 (scale_low/scale_high)
- **代码质量**: 共享 run_db() 消除重复、配置集中化 (.env)
- **前端**: SVG 迷你趋势线、实时告警 Toast、移动端响应式

### v1.1.0 (2026-03-19)
- 安全加固：移除所有写入功能，改为只读模式
- 代码质量优化：修复22个问题
- 新增功能：历史数据图表、知识库、程序管理
- 性能优化：添加配置常量、类型注解

## License

MIT License
