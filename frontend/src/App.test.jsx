import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("deleting the open graph asks first, then clears it", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "water" }));
  await screen.findByRole("heading", { name: "Rain" });
  const del = screen.getByRole("button", { name: "Delete water" });

  fireEvent.click(del);
  expect(fetch.mock.calls.some(([, o]) => o?.method === "DELETE")).toBe(false);

  fireEvent.click(del);
  await waitFor(() => {
    const call = fetch.mock.calls.find(([, o]) => o?.method === "DELETE");
    expect(String(call[0])).toMatch(/\/api\/graphs\/g1$/);
  });
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Rain" })).toBeNull());
  expect(confirm).toHaveBeenCalledTimes(2);
});

test("the graph is grown in the chosen language, and the report follows it", async () => {
  const sources = [];
  globalThis.EventSource = class {
    constructor(url) {
      sources.push(this);
      this.url = url;
    }
    close() {}
  };
  render(<App />);
  fireEvent.change(screen.getByLabelText("Concepts in"), { target: { value: "Nederlands" } });
  fireEvent.click(screen.getByRole("button", { name: "Plant" }));
  expect(new URL(sources[0].url, "http://x").searchParams.get("language")).toBe("Nederlands");
  act(() => sources[0].onmessage({ data: JSON.stringify({ done: true, graph_id: "g1" }) }));
  expect((await screen.findByRole("combobox", { name: "Report language" })).value).toBe("Nederlands");
});
