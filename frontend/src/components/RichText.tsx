import { memo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

// Convert LaTeX delimiters \( ... \) and \[ ... \] to $ and $$ for remark-math
function normalizeLatex(text: string): string {
  return text
    .replace(/\\\(/g, "$")
    .replace(/\\\)/g, "$")
    .replace(/\\\[/g, "$$")
    .replace(/\\\]/g, "$$");
}

// Memoized: markdown + KaTeX parsing is expensive, so only re-parse when the
// content string actually changes (not on every parent/list re-render).
export const RichText = memo(function RichText({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
    >
      {normalizeLatex(content)}
    </ReactMarkdown>
  );
});
