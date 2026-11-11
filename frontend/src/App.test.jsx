import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App.jsx";

// The force graph needs a real canvas; the app's own logic is what is under test here.
vi.mock("./components/GraphView.jsx", () => ({ GraphView: () => <div data-testid="graph" /> }));

const json = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });

const GRAPH = {
  id: "g1",
  seeds: ["water"],
  params: {},
  created_at: "2026-11-11T10:00:00Z",
  nodes: [
    { id: "water", label: "water", depth: 0 },
    { id: "rain", label: "rain", depth: 1 },
  ],
  edges: [{ source: "water", target: "rain" }],
};
const REPORT = {
  id: "r1",
  graph_id: "g1",
  title: "water",
  status: "done",
  created_at: "2026-11-11T10:01:00Z",
  sections: [
    { key: "intro", title: "", markdown: "Water is everywhere.", source_node_ids: ["water"] },
    { key: "s0", title: "Rain", markdown: "It falls.\n\n![rain](gen: rain on a window)", source_node_ids: ["rain"] },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn((url) => {
    const u = String(url);
    if (u.includes("/api/jobs")) return json([]);
    if (u.endsWith("/api/graphs")) return json([GRAPH]);
    if (u.endsWith("/api/graphs/g1")) return json(GRAPH);
    if (u.endsWith("/api/graphs/g1/reports")) return json([REPORT]);
    return json([]);
  });
});

test("reopening a saved graph shows its report with images", async () => {
  render(<App />);
  const open = await screen.findByRole("button", { name: "water" });
  fireEvent.click(open);
  await waitFor(() => expect(screen.getByRole("heading", { name: "Rain" })).toBeDefined());
  expect(screen.getByText("Water is everywhere.")).toBeDefined();
  expect(document.querySelector("figure.gen img").getAttribute("src")).toContain("/api/images?spec=");
  expect(screen.getByRole("button", { name: "Grow again" })).toBeDefined();
});
