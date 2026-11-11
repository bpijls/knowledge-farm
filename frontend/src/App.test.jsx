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
  style: "prose",
  created_at: "2026-11-11T10:01:00Z",
  sections: [
    { key: "intro", title: "", markdown: "Water is everywhere.", source_node_ids: ["water"] },
    { key: "s0", title: "Rain", markdown: "It falls.\n\n![rain](gen: rain on a window)", source_node_ids: ["rain"] },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn((url, options) => {
    const u = String(url);
    if (u.includes("/api/jobs")) return json([]);
    if (u.endsWith("/api/graphs")) return json([GRAPH]);
    if (u.endsWith("/api/graphs/g1")) return json(GRAPH);
    if (u.endsWith("/api/graphs/g1/reports")) {
      if (options?.method === "POST") return json({ report: { ...REPORT, status: "growing" }, job: { id: "j1" } });
      return json([REPORT]);
    }
    if (u.endsWith("/api/report-styles"))
      return json([
        { key: "prose", label: "Prose" },
        { key: "flyer", label: "Commercial flyer" },
      ]);
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

test("the chosen style is sent with a new report", async () => {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "water" }));
  const select = await screen.findByRole("combobox", { name: "Report style" });
  await screen.findByRole("option", { name: "Commercial flyer" });
  fireEvent.change(select, { target: { value: "flyer" } });
  fireEvent.click(await screen.findByRole("button", { name: "Grow again" }));
  await waitFor(() => {
    const post = fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(JSON.parse(post[1].body)).toEqual({ language: "English", style: "flyer" });
  });
});
