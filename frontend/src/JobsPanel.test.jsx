import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import JobsPanel from "./JobsPanel.jsx";
import { useJobs } from "./useJobs.js";

const job = (over = {}) => ({
  id: "j1", kind: "generate_items", subject: "items", status: "running",
  progress: "Writing", total: 4, done: 1, error: "", ...over,
});

let routes;

beforeEach(() => {
  routes = {};
  globalThis.fetch = vi.fn((url, options = {}) => {
    const key = `${options.method ?? "GET"} ${String(url).replace(/^.*\/api/, "")}`;
    const body = typeof routes[key] === "function" ? routes[key]() : routes[key];
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Harness({ onFinish }) {
  const { jobs, refresh } = useJobs({ onFinish, intervalMs: 1000 });
  return <JobsPanel jobs={jobs} refresh={refresh} />;
}

test("shows progress and the log of the running job", async () => {
  routes["GET /jobs"] = [job()];
  routes["GET /jobs/j1"] = { ...job(), log_text: "Planning\n  planned 3 item(s)\n" };

  render(<Harness />);

  await waitFor(() => expect(screen.getByText("Running")).toBeDefined());
  expect(screen.getByText("1 / 4")).toBeDefined();
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("25");
  await waitFor(() => expect(screen.getByText(/planned 3 item/)).toBeDefined());
});

test("cancel posts to the job and refreshes the list", async () => {
  let cancelled = false;
  routes["GET /jobs"] = () => [job(cancelled ? { status: "cancelled", progress: "" } : {})];
  routes["GET /jobs/j1"] = { ...job(), log_text: "" };
  routes["POST /jobs/j1/cancel"] = () => {
    cancelled = true;
    return job({ status: "cancelled" });
  };

  render(<Harness />);
  fireEvent.click(await screen.findByText("Cancel"));

  await waitFor(() => expect(screen.getByText("Cancelled")).toBeDefined());
  expect(screen.getByText("Retry")).toBeDefined();
  expect(screen.queryByText("Cancel")).toBeNull();
});

test("polls while a job is busy, reports when it finishes, then stops polling", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let status = "running";
  routes["GET /jobs"] = () => [job({ status })];
  routes["GET /jobs/j1"] = () => ({ ...job({ status }), log_text: "" });
  const onFinish = vi.fn();

  render(<Harness onFinish={onFinish} />);
  await waitFor(() => expect(screen.getByText("Running")).toBeDefined());

  status = "done";
  await act(() => vi.advanceTimersByTimeAsync(1000));
  await waitFor(() => expect(screen.getByText("Done")).toBeDefined());
  expect(onFinish).toHaveBeenCalledTimes(1);
  expect(onFinish.mock.calls[0][0].status).toBe("done");

  const listCalls = () => fetch.mock.calls.filter(([url]) => String(url).endsWith("/api/jobs")).length;
  const before = listCalls();
  await act(() => vi.advanceTimersByTimeAsync(5000));
  expect(listCalls()).toBe(before);
});

test("renders nothing when there are no jobs", async () => {
  routes["GET /jobs"] = [];
  const { container } = render(<Harness />);
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(container.querySelector(".jobs")).toBeNull();
});
