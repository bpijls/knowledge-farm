import { useState } from "react";

export const LANGUAGES = ["English", "Nederlands"];

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}


export function ConceptForm({ onSubmit, loading }) {
  const [seedsText, setSeedsText] = useState("water");
  const [iterations, setIterations] = useState(2);
  const [maxConcepts, setMaxConcepts] = useState(200);
  const [temperature, setTemperature] = useState(0.7);
  const [language, setLanguage] = useState(() => stored("kf-graph-language", LANGUAGES[0]));

  function chooseLanguage(value) {
    setLanguage(value);
    try {
      localStorage.setItem("kf-graph-language", value);
    } catch {
      /* private window: not remembered */
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    const seeds = seedsText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (seeds.length === 0) return;
    onSubmit({ seeds, iterations, maxConcepts, temperature, language });
  }

  return (
    <form onSubmit={handleSubmit} className="concept-form">
      <div className="field">
        <label>Seed concepts (one per line or comma-separated)</label>
        <textarea
          rows={4}
          value={seedsText}
          onChange={(e) => setSeedsText(e.target.value)}
          placeholder="machine learning&#10;consciousness&#10;black holes"
          disabled={loading}
        />
      </div>

      <div className="field">
        <label htmlFor="graph-language">Concepts in</label>
        <select
          id="graph-language"
          value={language}
          onChange={(e) => chooseLanguage(e.target.value)}
          disabled={loading}
        >
          {LANGUAGES.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </div>

      <div className="field-row">
        <div className="field">
          <label>Generations</label>
          <input
            type="number"
            min={1}
            max={10}
            value={iterations}
            onChange={(e) => setIterations(Number(e.target.value))}
            disabled={loading}
          />
        </div>
        <div className="field">
          <label>Max concepts</label>
          <input
            type="number"
            min={10}
            max={2000}
            value={maxConcepts}
            onChange={(e) => setMaxConcepts(Number(e.target.value))}
            disabled={loading}
          />
        </div>
      </div>

      <div className="field">
        <label>
          Temperature <span className="temp-value">{temperature.toFixed(2)}</span>
        </label>
        <input
          type="range"
          min={0}
          max={2}
          step={0.05}
          value={temperature}
          onChange={(e) => setTemperature(Number(e.target.value))}
          disabled={loading}
          className="temp-slider"
        />
        <div className="temp-hints">
          <span>focused</span>
          <span>wild</span>
        </div>
      </div>

      <button type="submit" disabled={loading} className="generate-btn">
        {loading ? "Growing…" : "Plant"}
      </button>
    </form>
  );
}
