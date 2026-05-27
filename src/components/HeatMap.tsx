import type { ModelMeta, ScoreRow } from '../types/leaderboard';

interface Props {
  /** column label → row data (per-model scores + optional n_queries/n_assertions) */
  columns: Record<string, ScoreRow>;
  models: ModelMeta[];
  /** Model id used as primary sort key (default: column average). */
  sortBy?: string;
  /** Minimum n_queries required to include a column. Default 2 (i.e. n > 1). */
  minNQueries?: number;
}

/** Soft teal monochrome ramp — distinct from the 3 model colors
 *  (blue / purple / orange) but in the same pastel family. */
const PALETTE_STOPS: { t: number; rgb: [number, number, number] }[] = [
  { t: 0.0,  rgb: [240, 247, 245] },
  { t: 0.25, rgb: [207, 232, 226] },
  { t: 0.5,  rgb: [146, 200, 188] },
  { t: 0.75, rgb: [ 72, 156, 138] },
  { t: 1.0,  rgb: [ 20, 110,  95] },
];

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function colorFor(value: number): string {
  const v = Math.max(0, Math.min(1, value));
  for (let i = 0; i < PALETTE_STOPS.length - 1; i++) {
    const lo = PALETTE_STOPS[i];
    const hi = PALETTE_STOPS[i + 1];
    if (v >= lo.t && v <= hi.t) {
      const t = (v - lo.t) / (hi.t - lo.t);
      const r = Math.round(lerp(lo.rgb[0], hi.rgb[0], t));
      const g = Math.round(lerp(lo.rgb[1], hi.rgb[1], t));
      const b = Math.round(lerp(lo.rgb[2], hi.rgb[2], t));
      return `rgb(${r}, ${g}, ${b})`;
    }
  }
  return 'rgb(200,200,200)';
}

function textColorFor(value: number): string {
  return value > 0.55 ? '#fff' : '#1c1f24';
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${Math.round(v * 100)}`;
}

export default function HeatMap({ columns, models, sortBy, minNQueries = 2 }: Props) {
  // 1. Filter out columns with n_queries < minNQueries (default 2 → keeps n > 1)
  let entries = Object.entries(columns).filter(([, row]) => {
    const n = row.n_queries;
    return n === undefined || n >= minNQueries;
  });

  // 2. Sort by `sortBy` model desc, else by mean across models desc
  entries.sort(([, aRow], [, bRow]) => {
    if (sortBy) {
      const a = (aRow[sortBy] as number) ?? -1;
      const b = (bRow[sortBy] as number) ?? -1;
      return b - a;
    }
    const meanA = models.reduce((s, m) => s + ((aRow[m.id] as number) ?? 0), 0) / models.length;
    const meanB = models.reduce((s, m) => s + ((bRow[m.id] as number) ?? 0), 0) / models.length;
    return meanB - meanA;
  });

  const colCount = entries.length;

  return (
    <div className="heatmap-scroll">
      <div
        className="heatmap-grid"
        style={{ gridTemplateColumns: `170px repeat(${colCount}, minmax(56px, 1fr))` }}
      >
        {/* Header row */}
        <div className="heatmap-corner" />
        {entries.map(([col]) => (
          <div className="heatmap-col-header" key={col} title={col}>
            <div className="heatmap-col-name">{col}</div>
          </div>
        ))}

        {/* One row per model */}
        {models.map((m) => (
          <div className="heatmap-model-row" key={m.id} style={{ display: 'contents' }}>
            <div className="heatmap-row-label">{m.display_name}</div>
            {entries.map(([col, row]) => {
              const v = row[m.id] as number | null | undefined;
              if (v === null || v === undefined) {
                return (
                  <div key={col} className="heatmap-cell heatmap-cell-missing" title="No data">
                    —
                  </div>
                );
              }
              return (
                <div
                  key={col}
                  className="heatmap-cell"
                  style={{ background: colorFor(v), color: textColorFor(v) }}
                  title={`${m.display_name} · ${col}: ${pct(v)}%`}
                >
                  {pct(v)}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
