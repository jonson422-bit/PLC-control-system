# PLC 智能管控系统

基于 OpenClaw 平台的 PLC 智能管控系统，支持 S7-200 SMART PLC 的监控、告警和 AI 故障诊断。

## 功能特性

- ✅ **实时监控**: 读取数字量 I/O 和模拟量 I/O
- ✅ **输出控制**: 远程控制 Q 输出点和模拟量输出
- ✅ **告警管理**: 创建告警规则，查看活动告警
- ✅ **AI 诊断**: 基于 Ollama 的故障智能诊断
- ✅ **Web Dashboard**: 现代化的监控界面
- ✅ **自然语言交互**: 通过 OpenClaw Skill 进行对话式操作

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  OpenClaw       │     │  FastAPI 后端   │     │  S7-200 SMART   │
│  Extension      │────▶│  Python 服务    │────▶│  PLC            │
│  + Skill        │     │  (端口 8080)    │     │  (192.168.2.1)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Ollama AI      │
                        │  (端口 11434)   │
                        └─────────────────┘
```

## 快速启动

### 1. 启动后端服务

```bash
cd /home/pi/OpenClaw_AI/extensions/plc-control
./start.sh
```

或手动启动：

```bash
source /home/pi/envs/plc_env/bin/activate
cd /home/pi/OpenClaw_AI/extensions/plc-control/backend/plc_service
python main.py
```

### 2. 访问 Dashboard

打开浏览器访问: http://192.168.1.16:8080

### 3. 在 OpenClaw 中使用 Skill

启动 OpenClaw 后，可以使用自然语言与 PLC 交互：

- "读取所有 PLC 输入点状态"
- "AIW16 的温度是多少"
- "打开 Q0.0"
- "设置告警：温度超过80度时提醒"
- "电机转速异常，帮我分析原因"

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/plc/read` | GET | 读取所有点位 |
| `/api/plc/read/{point}` | GET | 读取单个点位 |
| `/api/plc/write` | POST | 写入点位 |
| `/api/plc/cpu` | POST | CPU 控制 (start/stop) |
| `/api/alarms` | GET | 获取告警列表 |
| `/api/alarms/rules` | POST | 创建告警规则 |
| `/api/ai/diagnose` | POST | AI 故障诊断 |
| `/api/ai/analyze` | GET | 数据分析 |
| `/api/ai/recommend` | POST | 优化建议 |

完整 API 文档: http://192.168.1.16:8080/docs

## 支持的点位

### 数字量输入 (I0.0 - I0.7)
PLC 输入状态监控

### 数字量输出 (Q0.0 - Q0.7)
可远程控制的输出点

### 模拟量输入 (AIW16-22)
EM AT04 模块，4 路热电偶温度传感器

### 模拟量输出 (AQW32-34)
EM AQ02 模块，2 路模拟量输出

## 目录结构

```
extensions/plc-control/
├── index.ts                    # OpenClaw 扩展入口
├── openclaw.plugin.json        # 扩展配置
├── package.json
├── src/
│   └── tools/
│       ├── plc-read.ts         # PLC 读取工具
│       ├── plc-write.ts        # PLC 写入工具
│       ├── alarm-manage.ts     # 告警管理工具
│       └── ai-diagnose.ts      # AI 诊断工具
├── skills/
│   └── plc-expert/
│       └── SKILL.md            # 自然语言 Skill
├── backend/
│   └── plc_service/
│       ├── main.py             # FastAPI 主程序
│       ├── database.py         # SQLite 数据库
│       ├── plc_client.py       # PLC 通信客户端
│       ├── routes/             # API 路由
│       └── static/
│           └── dashboard.html  # Web Dashboard
└── start.sh                    # 启动脚本
```

## 配置

### 修改 PLC IP 地址

编辑 `backend/plc_service/plc_client.py`:

```python
def __init__(self, ip: str = '192.168.2.1', ...):
```

### 修改 AI 模型

编辑 `openclaw.plugin.json`:

```json
{
  "ollamaModel": "qwen2:7b"  // 或 deepseek-r1:7b, llama3:8b
}
```

## 依赖

- Python 3.11+
- FastAPI, uvicorn, httpx
- python-snap7 (已安装在 plc_env 虚拟环境)
- Ollama (本地运行)

## 故障排除

### PLC 连接失败
1. 检查 PLC IP 地址是否正确
2. 确认网络连通性: `ping 192.168.2.1`
3. 检查 snap7 库是否正确安装

### AI 诊断不可用
1. 确认 Ollama 服务运行: `systemctl status ollama`
2. 检查模型是否已下载: `ollama list`

### 扩展未加载
1. 在 OpenClaw 项目根目录运行: `pnpm build`
2. 重启 OpenClaw 服务
