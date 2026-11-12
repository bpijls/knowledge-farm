// Earlier harvests, to reopen without growing them again (also the offline backup for a demo).
export function SavedGraphs({ graphs, currentId, onOpen, onDelete }) {
  if (!graphs.length) return null;
  return (
    <details className="saved">
      <summary>Saved graphs ({graphs.length})</summary>
      <ul>
        {graphs.map((g) => (
          <li key={g.id} className={g.id === currentId ? "current" : undefined}>
            <button type="button" className="link" onClick={() => onOpen(g.id)}>
              {g.seeds.join(", ")}
            </button>
            <span className="saved-meta">{new Date(g.created_at).toLocaleDateString()}</span>
            <button
              type="button"
              className="saved-delete"
              aria-label={`Delete ${g.seeds.join(", ")}`}
              title="Delete this graph and its reports"
              onClick={() => onDelete(g)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
