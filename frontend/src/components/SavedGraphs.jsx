// Earlier harvests, to reopen without growing them again (also the offline backup for a demo).
export function SavedGraphs({ graphs, currentId, onOpen }) {
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
          </li>
        ))}
      </ul>
    </details>
  );
}
