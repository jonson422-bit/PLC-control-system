import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { z } from "zod";
import { registerPlcReadTool } from "./src/tools/plc-read.js";
import { registerPlcWriteTool } from "./src/tools/plc-write.js";
import { registerAlarmManageTool } from "./src/tools/alarm-manage.js";
import { registerAiDiagnoseTool } from "./src/tools/ai-diagnose.js";

const configSchema = z.object({
  backendUrl: z.string().default("http://localhost:8080"),
  refreshInterval: z.number().default(1000),
  enableAI: z.boolean().default(true),
  ollamaModel: z.string().default("qwen2:7b"),
});

type PlcControlConfig = z.infer<typeof configSchema>;

const plugin = {
  id: "plc-control",
  name: "PLC Control",
  description: "PLC智能管控系统 - 监控、告警、AI诊断",
  version: "1.0.0",
  configSchema,
  register(api: OpenClawPluginApi) {
    const config = api.getConfig<PlcControlConfig>();

    api.logger.info("PLC Control extension registering...", {
      backendUrl: config.backendUrl,
      enableAI: config.enableAI,
    });

    // 注册工具
    registerPlcReadTool(api, config);
    registerPlcWriteTool(api, config);
    registerAlarmManageTool(api, config);

    if (config.enableAI) {
      registerAiDiagnoseTool(api, config);
    }

    api.logger.info("PLC Control extension registered successfully");
  },
};

export default plugin;
