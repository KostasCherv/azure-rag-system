import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import type { NextRequest } from "next/server";

import { getAgentUrl } from "@/lib/agent-url";
import { getApimToken } from "@/lib/server-auth";
import { getUserId } from "@/lib/user-auth";

const serviceAdapter = new ExperimentalEmptyAdapter();

type Dependencies = {
  getToken: () => Promise<string | null>;
  getUrl: () => string;
  makeAgent: (url: string, headers: Record<string, string>) => HttpAgent;
  makeEndpoint: typeof copilotRuntimeNextJSAppRouterEndpoint;
};

export function createPostHandler(deps: Dependencies) {
  return async (request: NextRequest) => {
    const userId = getUserId(request.headers);
    if (!userId) {
      return new Response("Unauthorized", { status: 401 });
    }
    const token = await deps.getToken();
    const headers: Record<string, string> = { "X-RAG-User-ID": userId };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const runtime = new CopilotRuntime({
      agents: {
        default: deps.makeAgent(deps.getUrl(), headers),
      },
    });
    const { handleRequest } = deps.makeEndpoint({
      runtime,
      serviceAdapter,
      endpoint: "/api/copilotkit",
    });
    return handleRequest(request);
  };
}

export const POST = createPostHandler({
  getToken: getApimToken,
  getUrl: getAgentUrl,
  makeAgent: (url, headers) => new HttpAgent({ url, headers }),
  makeEndpoint: copilotRuntimeNextJSAppRouterEndpoint,
});
