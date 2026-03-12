import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { z } from "zod";

const configSchema = z.object({
  backendUrl: z.string().default("http://localhost:8080"),
  refreshInterval: z.number().default(1000),
  enableAI: z.boolean().default(true),
  ollamaModel: z.string().default("qwen2:7b"),
});

type PlcControlConfig = z.infer<typeof configSchema>;

/**
 * 注册告警管理工具
 */
export function registerAlarmManageTool(api: OpenClawPluginApi, config: PlcControlConfig) {
  // 获取告警列表
  api.registerTool({
    name: "plc_alarms",
    description: "获取 PLC 系统的活动告警列表。",
    parameters: z.object({
      status: z.enum(["active", "acknowledged", "all"]).optional().describe("告警状态过滤"),
    }),
    execute: async (params) => {
      const status = params.status || "active";
      try {
        const response = await fetch(`${config.backendUrl}/api/alarms?status=${status}`);
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 无法获取告警列表 (${error})`;
      }
    },
  });

  // 创建告警规则
  api.registerTool({
    name: "plc_alarm_rule_create",
    description: "创建 PLC 告警规则。例如：温度超过80度时告警。",
    parameters: z.object({
      point: z.string().describe("监控的点位名称，如 AIW16"),
      name: z.string().describe("规则名称"),
      condition: z.object({
        operator: z.enum([">", "<", ">=", "<=", "==", "!="]).describe("比较运算符"),
        value: z.number().describe("阈值"),
      }).describe("触发条件"),
      severity: z.enum(["info", "warning", "critical"]).optional().describe("严重程度"),
      message: z.string().optional().describe("告警消息"),
    }),
    execute: async (params) => {
      try {
        const response = await fetch(`${config.backendUrl}/api/alarm-rules`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return `告警规则创建成功: ${JSON.stringify(data, null, 2)}`;
      } catch (error) {
        return `错误: 无法创建告警规则 (${error})`;
      }
    },
  });

  // 确认告警
  api.registerTool({
    name: "plc_alarm_acknowledge",
    description: "确认告警，将其状态从 active 改为 acknowledged。",
    parameters: z.object({
      alarm_id: z.number().describe("告警ID"),
    }),
    execute: async (params) => {
      try {
        const response = await fetch(`${config.backendUrl}/api/alarms/${params.alarm_id}/acknowledge`, {
          method: "POST",
        });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 无法确认告警 (${error})`;
      }
    },
  });
}
