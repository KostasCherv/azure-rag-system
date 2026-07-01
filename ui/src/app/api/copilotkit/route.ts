import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import type { NextRequest } from "next/server";

import { getAgentUrl } from "@/lib/agent-url";

const runtime = new CopilotRuntime({
  agents: {
    default: new HttpAgent({ url: getAgentUrl() }),
  },
});

const serviceAdapter = new ExperimentalEmptyAdapter();

export async function POST(request: NextRequest) {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });

  return handleRequest(request);
}
