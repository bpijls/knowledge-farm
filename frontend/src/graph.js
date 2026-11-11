// Pure graph helpers, shared by App and GraphView.

// Must match backend/app/services/graph.py::normalize: it is how node ids are made.
export const normalize = (s) => s.trim().toLowerCase().replace(/\s+/g, " ");

function adjacency(edges) {
  const adj = new Map();
  const add = (a, b) => {
    if (!adj.has(a)) adj.set(a, []);
    adj.get(a).push(b);
  };
  for (const e of edges) {
    add(e.source, e.target);
    add(e.target, e.source);
  }
  return adj;
}

// Breadth-first search from the selected node to the nearest seed, returning the nodes
// ordered selected → … → root. A node cut off from every seed returns just itself.
export function pathToRoot(data, selectedId, seedIds) {
  if (!selectedId) return [];
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  if (!byId.has(selectedId)) return [];
  const adj = adjacency(data.edges);

  const prev = new Map([[selectedId, null]]);
  const queue = [selectedId];
  let root = null;
  while (queue.length) {
    const cur = queue.shift();
    if (seedIds.has(cur)) {
      root = cur;
      break;
    }
    for (const nb of adj.get(cur) ?? []) {
      if (!prev.has(nb)) {
        prev.set(nb, cur);
        queue.push(nb);
      }
    }
  }
  if (!root) return [byId.get(selectedId)];

  // `prev` points towards the selected node; unshifting from the root yields selected → root.
  const path = [];
  for (let id = root; id !== null; id = prev.get(id) ?? null) {
    const node = byId.get(id);
    if (node) path.unshift(node);
  }
  return path;
}

// Edge keys ("a|b" both ways) between consecutive nodes of a path.
export function pathEdgeKeys(path) {
  const set = new Set();
  for (let i = 0; i < path.length - 1; i++) {
    set.add(`${path[i].id}|${path[i + 1].id}`);
    set.add(`${path[i + 1].id}|${path[i].id}`);
  }
  return set;
}

// Edge keys of every edge whose both ends are in `ids` (a report section's subgraph).
export function inducedEdgeKeys(edges, ids) {
  const set = new Set();
  for (const e of edges) {
    if (ids.has(e.source) && ids.has(e.target)) {
      set.add(`${e.source}|${e.target}`);
      set.add(`${e.target}|${e.source}`);
    }
  }
  return set;
}
