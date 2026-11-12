import { useCallback, useEffect, useState } from "react";
import { getSession, login, logout } from "../api.js";

// Shows the app only once the site's access key has been given (or when none is required).
// Any 401 later on (cookie gone, key changed) brings the gate back via the "kf-locked" event.
export function KeyGate({ children }) {
  const [state, setState] = useState("checking"); // checking | locked | open
  const [required, setRequired] = useState(false);

  const check = useCallback(() => {
    getSession()
      .then((s) => {
        setRequired(s.required);
        setState(s.ok ? "open" : "locked");
      })
      .catch(() => setState("open")); // API unreachable: let the app show its own errors
  }, []);

  useEffect(() => {
    check();
    const lock = () => setState("locked");
    window.addEventListener("kf-locked", lock);
    return () => window.removeEventListener("kf-locked", lock);
  }, [check]);

  if (state === "checking") return null;
  if (state === "locked") return <KeyForm onOpen={() => setState("open")} />;
  return children({
    canLock: required,
    lock: () => logout().finally(() => setState("locked")),
  });
}

function KeyForm({ onOpen }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(key);
      onOpen();
    } catch {
      setError("That key doesn't open the gate.");
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form className="gate-card" onSubmit={submit}>
        <h1 className="title">Knowledge<br />Farm</h1>
        <p className="subtitle">seed vault · concept cultivator</p>
        <label className="gate-label" htmlFor="access-key">Access key</label>
        <input
          id="access-key"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        {error && <div className="error">{error}</div>}
        <button type="submit" className="harvest-btn" disabled={busy || !key.trim()}>
          {busy ? "Opening…" : "Open the gate"}
        </button>
      </form>
    </div>
  );
}
