"use client";

import { useDefaultRenderTool } from "@copilotkit/react-core/v2";
import { SearchDocsSources } from "./citations";

export function CitationToolRenderer() {
  useDefaultRenderTool({
    render: ({ name, status, result, toolCallId }) => {
      if (name !== "search_docs" || status !== "complete") return <></>;
      return <SearchDocsSources result={result} toolCallId={toolCallId} />;
    },
  });
  return null;
}
