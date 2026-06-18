import type { GenerateRequest, GraphData } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function generateGraph(req: GenerateRequest): Promise<GraphData> {
  const res = await fetch(`${BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function streamGraph(
  seeds: string[],
  iterations: number,
  maxConcepts: number,
  temperature: number,
  onDelta: (delta: { iteration: number; nodes: GraphData["nodes"]; edges: GraphData["edges"] }) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): EventSource {
  const params = new URLSearchParams({
    seeds: seeds.join(","),
    iterations: String(iterations),
    max_concepts: String(maxConcepts),
    temperature: String(temperature),
  });
  const es = new EventSource(`${BASE}/api/generate/stream?${params}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) {
      es.close();
      onDone();
    } else {
      onDelta(data);
    }
  };
  es.onerror = () => {
    es.close();
    onError(new Error("Stream connection error"));
  };
  return es;
}
