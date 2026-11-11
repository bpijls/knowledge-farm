import { useCallback, useEffect, useRef, useState } from "react";
import { listJobs } from "./api.js";

export const isBusy = (job) => job.status === "queued" || job.status === "running";

// Jobs run on the server, so nothing here keeps them alive: this only watches. It polls while
// something is busy, and catches up at once when the tab comes back into view (browsers
// throttle timers in background tabs).
export function useJobs({ subject, onFinish, intervalMs = 3000 } = {}) {
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const watching = useRef(new Set());
  const onFinishRef = useRef(onFinish);

  useEffect(() => {
    onFinishRef.current = onFinish;
  }, [onFinish]);

  const refresh = useCallback(async () => {
    try {
      const data = await listJobs(subject);
      for (const job of data) {
        if (isBusy(job)) watching.current.add(job.id);
        else if (watching.current.delete(job.id)) onFinishRef.current?.(job);
      }
      setJobs(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [subject]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const anyBusy = jobs.some(isBusy);
  useEffect(() => {
    if (!anyBusy) return;
    const timer = setInterval(refresh, intervalMs);
    return () => clearInterval(timer);
  }, [anyBusy, refresh, intervalMs]);

  useEffect(() => {
    const onVisible = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [refresh]);

  return { jobs, error, refresh, anyBusy };
}
