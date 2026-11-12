// All fetch() wrappers live here; components never call fetch directly.
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  // Locked out (no or expired access cookie): the gate in KeyGate.jsx asks for the key again.
  if (res.status === 401 && !path.startsWith("/login")) window.dispatchEvent(new Event("kf-locked"));
  if (!res.ok) throw new Error(`${options.method ?? "GET"} ${path} → ${res.status}`);
  return res.status === 204 ? null : res.json();
}

export const getHealth = () => request("/health");

// Access: one shared key, traded for an HttpOnly cookie (backend services/access.py).
export const getSession = () => request("/session");
export const login = (key) => request("/login", { method: "POST", body: JSON.stringify({ key }) });
export const logout = () => request("/logout", { method: "POST" });

// Graphs. Growing one streams over SSE: one message per iteration, then {done, graph_id}.
export function streamGraph({ seeds, iterations, maxConcepts, temperature }, { onDelta, onDone, onError }) {
  const params = new URLSearchParams({
    seeds: seeds.join(","),
    iterations: String(iterations),
    max_concepts: String(maxConcepts),
    temperature: String(temperature),
  });
  const es = new EventSource(`${BASE}/api/graphs/stream?${params}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) {
      es.close();
      onDone(data.graph_id);
    } else {
      onDelta(data);
    }
  };
  es.onerror = () => {
    es.close();
    onError(new Error("The graph stream was interrupted."));
  };
  return es;
}
export const listGraphs = () => request("/graphs");
export const getGraph = (id) => request(`/graphs/${id}`);
export const deleteGraph = (id) => request(`/graphs/${id}`, { method: "DELETE" });

// Reports: growing one queues a background job; the report row fills in as it runs.
export const growReport = (graphId, language, style) =>
  request(`/graphs/${graphId}/reports`, { method: "POST", body: JSON.stringify({ language, style }) });
export const listStyles = () => request("/report-styles");
export const listReports = (graphId) => request(`/graphs/${graphId}/reports`);
export const getReport = (id) => request(`/reports/${id}`);
export const reportMarkdownUrl = (id) => `${BASE}/api/reports/${id}/markdown`;
// The image for a gen: tag's spec; 404 until the job has drawn it.
export const imageUrl = (spec) => `${BASE}/api/images?spec=${encodeURIComponent(spec)}`;

// Background jobs: starting one returns immediately; progress comes from polling.
export const listJobs = (subject) =>
  request(`/jobs${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`);
export const getJob = (id) => request(`/jobs/${id}`);
export const cancelJob = (id) => request(`/jobs/${id}/cancel`, { method: "POST" });
export const retryJob = (id) => request(`/jobs/${id}/retry`, { method: "POST" });
