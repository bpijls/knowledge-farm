import { useMemo, useState } from "react";
import { streamGraph } from "./api";
import { ConceptForm } from "./components/ConceptForm";
import { GraphView } from "./components/GraphView";
import type { GraphNode, GraphEdge, GraphData } from "./types";
import "./App.css";

// Breadth-first search from the selected node to the nearest seed (root),
// returning the ordered list of nodes from the selected node up to the root.
function pathToRoot(
  data: GraphData,
  selectedId: string | null,
  seedIds: Set<string>,
): GraphNode[] {
  if (!selectedId) return [];
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  if (!byId.has(selectedId)) return [];

  const adj = new Map<string, string[]>();
  for (const e of data.edges) {
    (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target);
    (adj.get(e.target) ?? adj.set(e.target, []).get(e.target)!).push(e.source);
  }

  const prev = new Map<string, string | null>([[selectedId, null]]);
  const queue = [selectedId];
  let root: string | null = null;
  while (queue.length) {
    const cur = queue.shift()!;
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
  if (!root) return [byId.get(selectedId)!]; // disconnected from any seed

  // Walk from the root back along `prev` (which points towards the selected
  // node); unshifting yields the list ordered selected → … → root.
  const path: GraphNode[] = [];
  for (let id: string | null = root; id !== null; id = prev.get(id) ?? null) {
    const node = byId.get(id);
    if (node) path.unshift(node);
  }
  return path;
}

function App() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [seedIds, setSeedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [showLabels, setShowLabels] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const path = useMemo(
    () => pathToRoot(graphData, selectedId, seedIds),
    [graphData, selectedId, seedIds],
  );

  const pathIds = useMemo(() => new Set(path.map((n) => n.id)), [path]);
  const pathEdges = useMemo(() => {
    const set = new Set<string>();
    for (let i = 0; i < path.length - 1; i++) {
      set.add(`${path[i].id}|${path[i + 1].id}`);
      set.add(`${path[i + 1].id}|${path[i].id}`);
    }
    return set;
  }, [path]);

  function handleGenerate(
    seeds: string[],
    iterations: number,
    maxConcepts: number,
    temperature: number,
  ) {
    setError(null);
    setLoading(true);
    setStatus("Starting…");
    setSelectedId(null);

    const nodes = new Map<string, GraphNode>();
    const edges = new Map<string, GraphEdge>();

    const newSeedIds = new Set(
      seeds.map((s) => s.trim().toLowerCase().replace(/\s+/g, " ")),
    );
    setSeedIds(newSeedIds);
    setGraphData({ nodes: [], edges: [] });

    streamGraph(
      seeds,
      iterations,
      maxConcepts,
      temperature,
      (delta) => {
        for (const n of delta.nodes) nodes.set(n.id, n);
        for (const e of delta.edges) edges.set(`${e.source}||${e.target}`, e);
        setGraphData({ nodes: [...nodes.values()], edges: [...edges.values()] });
        setStatus(
          `Generation ${delta.iteration} · ${nodes.size} concept${nodes.size !== 1 ? "s" : ""}, ${edges.size} link${edges.size !== 1 ? "s" : ""}`,
        );
      },
      () => {
        setLoading(false);
        setStatus(`Grown · ${nodes.size} concepts, ${edges.size} links`);
      },
      (err) => {
        setLoading(false);
        setError(err.message);
        setStatus("");
      },
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="title">Knowledge<br />Farm</h1>
        <p className="subtitle">seed vault · concept cultivator</p>
        <ConceptForm onSubmit={handleGenerate} loading={loading} />
        <label className="toggle">
          <input
            type="checkbox"
            checked={showLabels}
            onChange={(e) => setShowLabels(e.target.checked)}
          />
          Show labels
        </label>
        {status && <p className="status">{status}</p>}
        {error && <div className="error">{error}</div>}

        {path.length > 0 && (
          <div className="path-panel">
            <h2 className="path-title">Trace to seed</h2>
            <ol className="path-list">
              {path.map((n, i) => (
                <li
                  key={n.id}
                  className={
                    i === 0
                      ? "path-selected"
                      : i === path.length - 1
                        ? "path-root"
                        : undefined
                  }
                >
                  {n.label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </aside>

      <main className="main">
        {graphData.nodes.length === 0 && !loading ? (
          <div className="empty">Plant a few seed concepts to watch the graph grow</div>
        ) : (
          <GraphView
            data={graphData}
            seedIds={seedIds}
            showLabels={showLabels}
            selectedId={selectedId}
            pathIds={pathIds}
            pathEdges={pathEdges}
            onSelectNode={setSelectedId}
          />
        )}
      </main>
    </div>
  );
}

export default App;
