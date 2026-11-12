import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getGraph,
  getReport,
  growReport,
  listGraphs,
  deleteGraph,
  listReports,
  listStyles,
  streamGraph,
} from "./api.js";
import { ConceptForm } from "./components/ConceptForm.jsx";
import { GraphView } from "./components/GraphView.jsx";
import { ReportView } from "./components/ReportView.jsx";
import { SavedGraphs } from "./components/SavedGraphs.jsx";
import { inducedEdgeKeys, normalize, pathEdgeKeys, pathToRoot } from "./graph.js";
import JobsPanel from "./JobsPanel.jsx";
import { isBusy, useJobs } from "./useJobs.js";
import { useResizable } from "./useResizable.js";

const LANGUAGES = ["English", "Nederlands"];
const EMPTY = { nodes: [], edges: [] };

// Until /api/report-styles answers, only the default is offered.
const DEFAULT_STYLES = [{ key: "prose", label: "Prose" }];

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private window: just don't remember it */
  }
}

const sidebarMax = () => Math.max(260, window.innerWidth * 0.4);
const reportMax = () => Math.max(340, window.innerWidth - 560);

export default function App({ access = { canLock: false, lock: () => {} } }) {
  // Panel widths: undefined until dragged, so the stylesheet's defaults apply.
  const sidebar = useResizable("kf-sidebar-w", { min: 240, max: sidebarMax, sign: 1 });
  const reportPanel = useResizable("kf-report-w", { min: 320, max: reportMax, sign: -1 });
  const [graphData, setGraphData] = useState(EMPTY);
  const [graphId, setGraphId] = useState(null);
  const [seedIds, setSeedIds] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("");
  const [showLabels, setShowLabels] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [saved, setSaved] = useState([]);

  const [report, setReport] = useState(null);
  // Every report grown from the open graph, newest first, to switch between versions.
  const [versions, setVersions] = useState([]);
  const [reportJobId, setReportJobId] = useState(null);
  const [hoverKey, setHoverKey] = useState(null);
  const [pinnedKey, setPinnedKey] = useState(null);
  const [language, setLanguage] = useState(() => stored("kf-language", LANGUAGES[0]));
  const [styles, setStyles] = useState(DEFAULT_STYLES);
  const [style, setStyle] = useState(() => stored("kf-style", "prose"));

  useEffect(() => {
    listStyles()
      .then((list) => list.length && setStyles(list))
      .catch(() => {});
  }, []);

  const refreshSaved = useCallback(() => listGraphs().then(setSaved).catch(() => {}), []);
  useEffect(() => {
    refreshSaved();
  }, [refreshSaved]);

  // --- report ------------------------------------------------------------------------------
  const { jobs, refresh: refreshJobs } = useJobs({
    subject: `graph:${graphId ?? "none"}`,
    intervalMs: 2000,
  });
  // The job behind the open report: the one just started, else the graph's latest report job
  // (a reopened graph). Its status is the truth: a worker restart leaves the row "growing".
  const reportJob =
    jobs.find((j) => j.id === reportJobId) ?? jobs.find((j) => j.kind === "grow_report") ?? null;
  const growing = report?.status === "growing";
  const reportBusy = reportJob ? isBusy(reportJob) : growing;

  // While the report grows, re-read it so new sections appear as the job writes them.
  const polling = growing && reportBusy;
  useEffect(() => {
    if (!polling) return;
    const id = report.id;
    const timer = setInterval(() => {
      getReport(id).then(setReport).catch(() => {});
    }, 1500);
    return () => clearInterval(timer);
  }, [polling, report?.id]);

  // When the job finishes, one last read picks up the final state.
  useEffect(() => {
    if (report && reportJob && !isBusy(reportJob)) getReport(report.id).then(setReport).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportJob?.status]);

  async function onGrowReport() {
    setError(null);
    setHoverKey(null);
    setPinnedKey(null);
    try {
      const started = await growReport(graphId, language, style);
      setReport(started.report);
      setVersions((v) => [started.report, ...v]);
      setReportJobId(started.job.id);
      await refreshJobs();
    } catch (e) {
      setError(e.message);
    }
  }

  function chooseLanguage(value) {
    setLanguage(value);
    remember("kf-language", value);
  }

  function chooseStyle(value) {
    setStyle(value);
    remember("kf-style", value);
  }

  // --- highlight: a report section wins over a traced path ---------------------------------
  const activeKey = pinnedKey ?? hoverKey;
  const activeSection = report?.sections.find((s) => s.key === activeKey) ?? null;
  const path = useMemo(
    () => pathToRoot(graphData, selectedId, seedIds),
    [graphData, selectedId, seedIds]
  );
  const highlightIds = useMemo(
    () => (activeSection ? new Set(activeSection.source_node_ids) : new Set(path.map((n) => n.id))),
    [activeSection, path]
  );
  const highlightEdges = useMemo(
    () => (activeSection ? inducedEdgeKeys(graphData.edges, highlightIds) : pathEdgeKeys(path)),
    [activeSection, graphData.edges, highlightIds, path]
  );

  // Clicking a concept traces it to the seed and, with a report open, shows its section.
  function onSelectNode(id) {
    setSelectedId(id);
    setPinnedKey(null);
    if (!id || !report) return;
    const section = report.sections.find((s) => s.key !== "intro" && s.key !== "conclusion" && s.source_node_ids.includes(id));
    if (section) {
      setHoverKey(section.key);
      document.getElementById(`section-${section.key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // --- growing and opening graphs ----------------------------------------------------------
  function resetView() {
    setSelectedId(null);
    setReport(null);
    setVersions([]);
    setReportJobId(null);
    setHoverKey(null);
    setPinnedKey(null);
    setError(null);
  }

  function handleGenerate({ seeds, iterations, maxConcepts, temperature }) {
    resetView();
    setLoading(true);
    setStatus("Starting…");
    setGraphId(null);
    setSeedIds(new Set(seeds.map(normalize)));
    setGraphData(EMPTY);

    const nodes = new Map();
    const edges = new Map();
    streamGraph(
      { seeds, iterations, maxConcepts, temperature },
      {
        onDelta: (delta) => {
          for (const n of delta.nodes) nodes.set(n.id, n);
          for (const e of delta.edges) edges.set(`${e.source}||${e.target}`, e);
          setGraphData({ nodes: [...nodes.values()], edges: [...edges.values()] });
          setStatus(`Generation ${delta.iteration} · ${nodes.size} concepts, ${edges.size} links`);
        },
        onDone: (id) => {
          setLoading(false);
          setGraphId(id);
          setStatus(`Grown · ${nodes.size} concepts, ${edges.size} links`);
          refreshSaved();
        },
        onError: (err) => {
          setLoading(false);
          setError(err.message);
          setStatus("");
        },
      }
    );
  }

  async function openGraph(id) {
    resetView();
    try {
      const graph = await getGraph(id);
      setGraphId(graph.id);
      setSeedIds(new Set(graph.nodes.filter((n) => n.depth === 0).map((n) => n.id)));
      setGraphData({ nodes: graph.nodes, edges: graph.edges });
      setStatus(`Reopened · ${graph.nodes.length} concepts, ${graph.edges.length} links`);
      const reports = await listReports(graph.id);
      setVersions(reports);
      if (reports.length) setReport(reports[0]);
    } catch (e) {
      setError(e.message);
    }
  }

  async function removeGraph(g) {
    const name = g.seeds.join(", ");
    if (!window.confirm(`Delete "${name}" and all its reports? This cannot be undone.`)) return;
    try {
      await deleteGraph(g.id);
      if (g.id === graphId) {
        resetView();
        setGraphId(null);
        setGraphData(EMPTY);
        setStatus("");
      }
      refreshSaved();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div
      className={`app${report ? " with-report" : ""}`}
      style={{
        ...(sidebar.width && { "--sidebar-w": `${sidebar.width}px` }),
        ...(reportPanel.width && { "--report-w": `${reportPanel.width}px` }),
      }}
    >
      <aside className="sidebar">
        <h1 className="title">Knowledge<br />Farm</h1>
        <p className="subtitle">seed vault · concept cultivator</p>
        <ConceptForm onSubmit={handleGenerate} loading={loading} />
        <label className="toggle">
          <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
          Show labels
        </label>
        {status && <p className="status">{status}</p>}
        {error && <div className="error">{error}</div>}

        {graphId && !loading && (
          <div className="harvest">
            <div className="harvest-row">
              <select value={style} onChange={(e) => chooseStyle(e.target.value)} aria-label="Report style">
                {styles.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
              <select value={language} onChange={(e) => chooseLanguage(e.target.value)} aria-label="Report language">
                {LANGUAGES.map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </div>
            <button type="button" className="harvest-btn" onClick={onGrowReport} disabled={reportBusy}>
              {reportBusy ? "Growing report…" : report ? "Grow again" : "Grow report"}
            </button>
          </div>
        )}

        {path.length > 0 && !activeSection && (
          <div className="path-panel">
            <h2 className="path-title">Trace to seed</h2>
            <ol className="path-list">
              {path.map((n, i) => (
                <li
                  key={n.id}
                  className={i === 0 ? "path-selected" : i === path.length - 1 ? "path-root" : undefined}
                >
                  {n.label}
                </li>
              ))}
            </ol>
          </div>
        )}

        <SavedGraphs graphs={saved} currentId={graphId} onOpen={openGraph} onDelete={removeGraph} />
        {jobs.length > 0 && (
          <details className="saved">
            <summary>Jobs</summary>
            <JobsPanel jobs={jobs} refresh={refreshJobs} />
          </details>
        )}
        {access.canLock && (
          <button type="button" className="link lock" onClick={access.lock}>
            Lock this browser
          </button>
        )}
      </aside>
      <div className="resizer" aria-label="Resize the sidebar" {...sidebar.handleProps} />

      <main className="main">
        {graphData.nodes.length === 0 && !loading ? (
          <div className="empty">Plant a seed concept to watch the graph grow</div>
        ) : (
          <GraphView
            data={graphData}
            seedIds={seedIds}
            showLabels={showLabels}
            selectedId={selectedId}
            pathIds={highlightIds}
            pathEdges={highlightEdges}
            onSelectNode={onSelectNode}
          />
        )}
      </main>

      {report && <div className="resizer" aria-label="Resize the report" {...reportPanel.handleProps} />}
      {report && (
        <ReportView
          report={report}
          styleLabel={styles.find((s) => s.key === report.style)?.label}
          versions={versions}
          styleName={(key) => styles.find((s) => s.key === key)?.label ?? key}
          onPickVersion={async (id) => {
            setHoverKey(null);
            setPinnedKey(null);
            try {
              setReport(await getReport(id));
            } catch (e) {
              setError(e.message);
            }
          }}
          job={reportJob}
          activeKey={activeKey}
          pinnedKey={pinnedKey}
          onHover={setHoverKey}
          onPin={setPinnedKey}
          onClose={() => {
            setReport(null);
            setHoverKey(null);
            setPinnedKey(null);
          }}
        />
      )}
    </div>
  );
}
