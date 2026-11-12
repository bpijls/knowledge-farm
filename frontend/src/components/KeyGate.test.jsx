import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { KeyGate } from "./KeyGate.jsx";

const reply = (status, body = null) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

test("asks for the key, then opens; a later 401 locks it again", async () => {
  globalThis.fetch = vi.fn((url, options) => {
    const u = String(url);
    if (u.endsWith("/api/session")) return reply(200, { required: true, ok: false });
    if (u.endsWith("/api/login")) return JSON.parse(options.body).key === "sesame" ? reply(204) : reply(401);
    return reply(204);
  });
  render(<KeyGate>{() => <p>inside</p>}</KeyGate>);

  const input = await screen.findByLabelText("Access key");
  fireEvent.change(input, { target: { value: "guess" } });
  fireEvent.click(screen.getByRole("button", { name: "Open the gate" }));
  await screen.findByText("That key doesn't open the gate.");
  expect(screen.queryByText("inside")).toBeNull();

  fireEvent.change(input, { target: { value: "sesame" } });
  fireEvent.click(screen.getByRole("button", { name: "Open the gate" }));
  await screen.findByText("inside");

  act(() => window.dispatchEvent(new Event("kf-locked")));
  await waitFor(() => expect(screen.getByLabelText("Access key")).toBeDefined());
});

test("no key configured: straight in", async () => {
  globalThis.fetch = vi.fn(() => reply(200, { required: false, ok: true }));
  render(<KeyGate>{({ canLock }) => <p>inside {String(canLock)}</p>}</KeyGate>);
  await screen.findByText("inside false");
});
