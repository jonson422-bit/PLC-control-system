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
 * 注册 AI 诊断工具
 */
export function registerAiDiagnoseTool(api: OpenClawPluginApi, config: PlcControlConfig) {
  // 故障诊断
  api.registerTool({
    name: "plc_diagnose",
    description: "使用 AI 分析 PLC 故障。输入故障现象描述，AI 会分析可能的原因并给出排查建议。",
    parameters: z.object({
      symptom: z.string().describe("故障现象描述，如：电机转速异常、温度过高等"),
      context: z.string().optional().describe("额外上下文信息"),
    }),
    execute: async (params) => {
      try {
        const response = await fetch(`${config.backendUrl}/api/ai/diagnose`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symptom: params.symptom,
            context: params.context || "",
            model: config.ollamaModel,
          }),
        });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return data.analysis || JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: AI 诊断服务不可用 (${error})`;
      }
    },
  });

  // 数据分析
  api.registerTool({
    name: "plc_analyze",
    description: "对 PLC 监控数据进行智能分析，生成统计报告和趋势分析。",
    parameters: z.object({
      point: z.string().optional().describe("要分析的点位，不指定则分析所有"),
      period: z.enum(["1h", "6h", "24h", "7d"]).optional().describe("分析时间范围"),
    }),
    execute: async (params) => {
      try {
        const queryParams = new URLSearchParams();
        if (params.point) queryParams.set("point", params.point);
        if (params.period) queryParams.set("period", params.period);

        const response = await fetch(`${config.backendUrl}/api/ai/analyze?${queryParams}`);
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return data.summary || JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 数据分析服务不可用 (${error})`;
      }
    },
  });

  // 优化建议
  api.registerTool({
    name: "plc_recommend",
    description: "基于当前 PLC 运行状态，给出优化建议。",
    parameters: z.object({
      focus: z.enum(["energy", "efficiency", "safety", "all"]).optional().describe("优化关注点"),
    }),
    execute: async (params) => {
      try {
        const response = await fetch(`${config.backendUrl}/api/ai/recommend`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ focus: params.focus || "all" }),
        });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        const data = await response.json();
        return data.recommendations || JSON.stringify(data, null, 2);
      } catch (error) {
        return `错误: 优化建议服务不可用 (${error})`;
      }
    },
  });
}
