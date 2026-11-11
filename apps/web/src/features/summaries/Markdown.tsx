import "katex/dist/katex.min.css";

import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { safeUrl } from "./safeUrl";

/**
 * Safe Markdown for model output (spec 006 AC14): no raw HTML (no rehype-raw), links only to
 * http(s) and mailto with rel="noopener noreferrer nofollow", math via KaTeX with trust: false.
 */
const components: Components = {
  a: ({ href, children }) =>
    href ? (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="underline">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="ml-5 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="ml-5 list-decimal space-y-1">{children}</ol>,
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="font-reading leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { trust: false, strict: "ignore", throwOnError: false }]]}
        urlTransform={safeUrl}
        skipHtml
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
