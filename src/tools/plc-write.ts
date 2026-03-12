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
 * 注册 PLC 写入工具
 */
export function registerPlcWriteTool(api: OpenClawPluginApi, config: PlcControlConfig) {
  api.registerTool({
    name: "plc_write",
    description: "向 PLC 点位写入数据。只能写入输出点(Q)和模拟量输出(AQW)。",
    parameters: z.object({
      point: z.string().describe("要写入的点位名称，如 Q0.0, AQW32"),
      value: z.union([z.string(), z.number()]).describe("要写入的值。数字量: ON/OFF, 模拟量: 0-27648"),
    }),
    execute: async (params) => {
      try {
        const response = await fetch(`${config.backendUrl}/api/plc/write`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            point: params.point,
            value: params.value,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error: ${response.status}`);
        }
        const data = await response.json();
        return JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 无法写入 PLC (${error})`;
      }
    },
  });
}
