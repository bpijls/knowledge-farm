import { useEffect, useMemo, useRef } from "react";
import { reportMarkdownUrl } from "../api.js";
import { renderMarkdown } from "../markdown.js";

// The report as it grows: sections appear as the job writes them, images as it draws them.
// Hovering a section highlights the concepts it grew from; clicking pins that highlight.
export function ReportView({
  report,
  styleLabel,
  versions = [],
  styleName = (key) => key,
  onPickVersion,
  job,
  activeKey,
  pinnedKey,
  onHover,
  onPin,
  onClose,
}) {
  const bodyRef = useRef(null);
  // A new value whenever the job makes progress, so images that were not drawn yet are retried.
  const bust = job ? `${job.done}-${job.status}` : "";

  const sections = useMemo(
    () => report.sections.map((s) => ({ ...s, html: renderMarkdown(s.markdown, { bust }) })),
    [report.sections, bust]
  );

  // Images that 404 (not drawn yet, or failed) show a placeholder instead of a broken icon.
  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    for (const img of root.querySelectorAll("figure.gen img")) {
      const fig = img.closest("figure");
      img.onload = () => fig.classList.remove("pending");
      img.onerror = () => fig.classList.add("pending");
      if (img.complete && img.naturalWidth === 0) fig.classList.add("pending");
    }
  }, [sections]);

  const busy = job && (job.status === "queued" || job.status === "running");
  const percent = job?.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <aside className={`report report-style-${report.style ?? "prose"}`} aria-label="Report">
      <header className="report-head">
        <div>
          <p className="report-kicker">Harvest{styleLabel ? ` · ${styleLabel}` : ""}</p>
          <h2 className="report-title">{report.title}</h2>
        </div>
        <div className="report-actions">
          {versions.length > 1 && (
            <select
              className="quiet-btn"
              value={report.id}
              onChange={(e) => onPickVersion(e.target.value)}
              aria-label="Report version"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {styleName(v.style)} ·{" "}
                  {new Date(v.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </option>
              ))}
            </select>
          )}
          {report.status === "done" && (
            <a className="quiet-btn" href={reportMarkdownUrl(report.id)} target="_blank" rel="noreferrer">
              .md
            </a>
          )}
          <button type="button" className="quiet-btn" onClick={onClose} aria-label="Close report">
            ×
          </button>
        </div>
      </header>

      {busy && (
        <div className="report-progress">
          <div className="job-bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${percent}%` }} />
          </div>
          <p>{job.progress || "Waiting for the worker…"}</p>
        </div>
      )}
      {job?.status === "failed" && <div className="error">{job.error}</div>}

      <div className="report-body" ref={bodyRef} onMouseLeave={() => onHover(null)}>
        {sections.map((s) => (
          <section
            key={s.key}
            id={`section-${s.key}`}
            className={`report-section${activeKey === s.key ? " active" : ""}${pinnedKey === s.key ? " pinned" : ""}`}
            onMouseEnter={() => onHover(s.key)}
            onClick={() => onPin(pinnedKey === s.key ? null : s.key)}
          >
            {s.title && <h3>{s.title}</h3>}
            <div dangerouslySetInnerHTML={{ __html: s.html }} />
          </section>
        ))}
        {busy && <p className="report-growing">growing…</p>}
      </div>
    </aside>
  );
}
