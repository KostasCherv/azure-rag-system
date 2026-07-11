import type { NextRequest } from "next/server";

import { getBackendBaseUrl } from "@/lib/agent-url";
import { getApimToken } from "@/lib/server-auth";
import { getUserPrincipal, isUserAuthRequired } from "@/lib/user-auth";

type RouteContext = { params: Promise<{ path?: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const principal = getUserPrincipal(request.headers);
  if (isUserAuthRequired() && !principal) return new Response("Unauthorized", { status: 401 });
  const userId = principal?.oid ?? "local-development-user";
  try {
    const token = await getApimToken();
    const { path = [] } = await context.params;
    const target = new URL(`${getBackendBaseUrl()}/sessions${path.length ? `/${path.map(encodeURIComponent).join("/")}` : ""}`);
    target.search = request.nextUrl.search;
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-RAG-User-ID": userId,
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    const contentType = request.headers.get("content-type");
    const ifMatch = request.headers.get("if-match");
    if (contentType) headers["Content-Type"] = contentType;
    if (ifMatch) headers["If-Match"] = ifMatch;
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: response.status === 204 ? undefined : { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "session persistence unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
