import { expect, test } from "vitest";
import { genSpecs, renderMarkdown } from "./markdown.js";

test("gen: tags become figures pointing at the image endpoint", () => {
  const html = renderMarkdown("Text.\n\n![a fox](gen: a red fox, watercolour | 1280x720)", { bust: "3-running" });
  expect(html).toContain('<figure class="gen" data-spec="a red fox, watercolour | 1280x720">');
  expect(html).toContain(
    `src="/api/images?spec=${encodeURIComponent("a red fox, watercolour | 1280x720")}&amp;v=3-running"`
  );
  expect(html).toContain("<figcaption>a fox</figcaption>");
  expect(html).not.toContain("gen:");
});

test("ordinary images and html are left alone or escaped", () => {
  const html = renderMarkdown("![x](pic.png) <script>alert(1)</script>");
  expect(html).toContain('<img src="pic.png" alt="x">');
  expect(html).not.toContain("<script>");
});

test("genSpecs lists every tag", () => {
  expect(genSpecs("![a](gen: one) and ![b](GEN: two | 512x512)")).toEqual(["one", "two | 512x512"]);
});

test("a tag without gen: is treated as one", () => {
  const html = renderMarkdown("![m](3D render of a molecule, blue)");
  expect(html).toContain('data-spec="3D render of a molecule, blue"');
});

test("single newlines are line breaks (poems, flyer lists)", () => {
  expect(renderMarkdown("De grond ademt,\neen stil gebed")).toContain("De grond ademt,<br>");
});
