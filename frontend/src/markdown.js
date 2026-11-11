import MarkdownIt from "markdown-it";
import { imageUrl } from "./api.js";

// Report sections are Markdown with `![alt](gen: prompt | 1280x720)` tags. The tag stays in
// the text; here its src becomes the cached image's URL, and the image shows a placeholder
// until the job has drawn it (see ReportView: a failed load retries on the next refresh).

const md = new MarkdownIt({ html: false, linkify: true, typographer: true });

// markdown-it refuses link targets with spaces, so turn each gen: tag into a token it accepts
// before parsing and restore the spec in the image rule.
const GEN_TAG = /!\[([^\]\n]*)\]\(\s*gen:\s*([^)\n]*)\)/gi;

export function genSpecs(text) {
  return [...text.matchAll(GEN_TAG)].map((m) => m[2].trim());
}

md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx];
  const src = token.attrGet("src") ?? "";
  const alt = self.renderInlineAsText(token.children ?? [], options, env);
  const spec = src.startsWith("gen-spec:") ? decodeURIComponent(src.slice(9)) : null;
  if (spec === null) {
    return `<img src="${md.utils.escapeHtml(src)}" alt="${md.utils.escapeHtml(alt)}">`;
  }
  const url = `${imageUrl(spec)}${env?.bust ? `&v=${env.bust}` : ""}`;
  return (
    `<figure class="gen" data-spec="${md.utils.escapeHtml(spec)}">` +
    `<img src="${md.utils.escapeHtml(url)}" alt="${md.utils.escapeHtml(alt)}" loading="lazy">` +
    `<figcaption>${md.utils.escapeHtml(alt)}</figcaption></figure>`
  );
};

// `![alt](a prompt with spaces)`: a tag where the model forgot `gen:` (the job repairs these;
// reports written before that still have them).
const BARE_PROMPT = /!\[([^\]\n]*)\]\(\s*(?!gen:|https?:\/\/|\/|\.)([^)\n]*\s[^)\n]*)\)/gi;

export function renderMarkdown(text, { bust } = {}) {
  const prepared = text.replace(BARE_PROMPT, (_, alt, spec) => `![${alt}](gen: ${spec.trim()})`).replace(
    GEN_TAG,
    (_, alt, spec) => `![${alt}](gen-spec:${encodeURIComponent(spec.trim())})`
  );
  return md.render(prepared, { bust });
}
