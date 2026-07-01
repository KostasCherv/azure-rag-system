"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="default"
      showDevConsole={false}
      enableInspector={false}
      onError={(event) => {
        console.error("[CopilotKit]", event);
      }}
    >
      {children}
    </CopilotKit>
  );
}
