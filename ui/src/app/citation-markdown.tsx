"use client";

import { CopilotChatAssistantMessage } from "@copilotkit/react-core/v2";
import type { ComponentProps } from "react";
import { scrollToCitation } from "./citations";

const CITATION_MARKER_RE = /\[(\d{1,2})\](?!\()/g;

export function linkifyCitations(text: string): string {
  return text.replace(CITATION_MARKER_RE, "[$1](#cite-$1)");
}

type AnchorProps = ComponentProps<"a">;

export function CitationAnchor({ href, children, ...props }: AnchorProps) {
  if (href?.startsWith("#cite-")) {
    const citationId = Number(href.slice("#cite-".length));
    if (!Number.isFinite(citationId)) {
      return (
        <a href={href} {...props}>
          {children}
        </a>
      );
    }
    return (
      <button
        type="button"
        className="citation-marker"
        aria-label={`Go to source ${citationId}`}
        onClick={(event) => scrollToCitation(event.currentTarget, citationId)}
      >
        {children}
      </button>
    );
  }

  return (
    <a href={href} {...props}>
      {children}
    </a>
  );
}

export function CitationMarkdownRenderer({
  content,
  components,
  ...props
}: ComponentProps<typeof CopilotChatAssistantMessage.MarkdownRenderer>) {
  return (
    <CopilotChatAssistantMessage.MarkdownRenderer
      content={linkifyCitations(content)}
      components={{ ...components, a: CitationAnchor }}
      {...props}
    />
  );
}
