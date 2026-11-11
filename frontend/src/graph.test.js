import { expect, test } from "vitest";
import { inducedEdgeKeys, normalize, pathEdgeKeys, pathToRoot } from "./graph.js";

const data = {
  nodes: [
    { id: "water", label: "Water", depth: 0 },
    { id: "rain", label: "rain", depth: 1 },
    { id: "cloud", label: "cloud", depth: 2 },
    { id: "island", label: "island", depth: 2 },
  ],
  edges: [
    { source: "water", target: "rain" },
    { source: "rain", target: "cloud" },
  ],
};

test("normalize matches the backend", () => {
  expect(normalize("  Machine   Learning ")).toBe("machine learning");
});

test("pathToRoot walks from the selection to the nearest seed", () => {
  const path = pathToRoot(data, "cloud", new Set(["water"]));
  expect(path.map((n) => n.id)).toEqual(["cloud", "rain", "water"]);
  expect(pathEdgeKeys(path).has("rain|cloud")).toBe(true);
  expect(pathEdgeKeys(path).has("cloud|rain")).toBe(true);
});

test("a node cut off from every seed is its own path", () => {
  expect(pathToRoot(data, "island", new Set(["water"])).map((n) => n.id)).toEqual(["island"]);
  expect(pathToRoot(data, null, new Set(["water"]))).toEqual([]);
});

test("inducedEdgeKeys keeps edges inside a set of nodes", () => {
  const keys = inducedEdgeKeys(data.edges, new Set(["rain", "cloud"]));
  expect([...keys].sort()).toEqual(["cloud|rain", "rain|cloud"]);
});
