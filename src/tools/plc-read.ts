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
 * 注册 PLC 读取工具
 */
export function registerPlcReadTool(api: OpenClawPluginApi, config: PlcControlConfig) {
  api.registerTool({
    name: "plc_read",
    description: "读取 PLC 点位的实时数据。支持数字量输入(I)、数字量输出(Q)、模拟量输入(AIW)、模拟量输出(AQW)。",
    parameters: z.object({
      point: z.string().optional().describe("要读取的点位名称，如 I0.0, Q0.0, AIW16, AQW32。不指定则读取所有点位。"),
      device_id: z.number().optional().describe("设备ID，默认为1"),
    }),
    execute: async (params) => {
      const url = params.point
        ? `${config.backendUrl}/api/plc/read/${params.point}`
        : `${config.backendUrl}/api/plc/read`;

      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error: ${response.status}`);
        }
        const data = await response.json();
        return JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 无法连接到 PLC 后端服务 (${config.backendUrl})。请确保服务已启动。`;
      }
    },
  });
}
