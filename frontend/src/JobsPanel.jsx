import { useEffect, useRef, useState } from "react";
import { cancelJob, getJob, retryJob } from "./api.js";
import { isBusy } from "./useJobs.js";

const LABELS = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

// List of background jobs with progress, a log for the open one, and cancel / retry.
// `jobs` and `refresh` come from useJobs().
export default function JobsPanel({ jobs, refresh }) {
  const [openId, setOpenId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const logRef = useRef(null);

  // Open whatever is running, unless the user already picked a job.
  useEffect(() => {
    if (openId) return;
    const busy = jobs.find(isBusy);
    if (busy) setOpenId(busy.id);
  }, [jobs, openId]);

  // The list leaves out the log; fetch it for the open job each time the list refreshes.
  useEffect(() => {
    if (!openId) return;
    let stale = false;
    getJob(openId)
      .then((job) => !stale && setDetail(job))
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [openId, jobs]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [detail]);

  async function act(action, id) {
    setError(null);
    try {
      await action(id);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!jobs.length) return null;

  return (
    <section className="jobs">
      <h2>Jobs</h2>
      {error && <p className="error">{error}</p>}
      <ul>
        {jobs.map((job) => {
          const open = job.id === openId;
          const percent = job.total ? Math.round((job.done / job.total) * 100) : 0;
          return (
            <li key={job.id} className="job">
              <div className="job-head">
                <button
                  type="button"
                  className="job-toggle"
                  aria-expanded={open}
                  onClick={() => setOpenId(open ? null : job.id)}
                >
                  <span className={`job-status job-status-${job.status}`}>
                    {LABELS[job.status] ?? job.status}
                  </span>
                  <span className="job-kind">{job.kind}</span>
                  <span className="job-count">
                    {job.total ? `${job.done} / ${job.total}` : ""}
                  </span>
                </button>
                {isBusy(job) && (
                  <button type="button" className="quiet" onClick={() => act(cancelJob, job.id)}>
                    Cancel
                  </button>
                )}
                {(job.status === "failed" || job.status === "cancelled") && (
                  <button type="button" className="quiet" onClick={() => act(retryJob, job.id)}>
                    Retry
                  </button>
                )}
              </div>
              {isBusy(job) && (
                <div className="job-bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
                  <div style={{ width: `${percent}%` }} />
                </div>
              )}
              {job.progress && <p className="job-progress">{job.progress}</p>}
              {job.error && <p className="error">{job.error}</p>}
              {open && detail?.id === job.id && (
                <pre className="job-log" ref={logRef}>
                  {detail.log_text || "No output yet."}
                </pre>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
