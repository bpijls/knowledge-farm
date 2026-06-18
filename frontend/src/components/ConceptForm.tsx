import { useState } from "react";

interface Props {
  onSubmit: (
    seeds: string[],
    iterations: number,
    maxConcepts: number,
    temperature: number,
  ) => void;
  loading: boolean;
}

export function ConceptForm({ onSubmit, loading }: Props) {
  const [seedsText, setSeedsText] = useState("machine learning");
  const [iterations, setIterations] = useState(2);
  const [maxConcepts, setMaxConcepts] = useState(200);
  const [temperature, setTemperature] = useState(0.7);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const seeds = seedsText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (seeds.length === 0) return;
    onSubmit(seeds, iterations, maxConcepts, temperature);
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
