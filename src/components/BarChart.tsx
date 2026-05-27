import type { ModelMeta } from '../types/leaderboard';

export interface BarDatum {
  modelId: string;
  label: string;
  color: string;
  /** point estimate (0-1) */
  value: number | null;
  /** optional CI bounds (0-1) for box-plot whiskers */
  ciLow?: number;
  ciHigh?: number;
}

interface Props {
  data: BarDatum[];
  /** Optional dotted baseline (0-1) */
  baseline?: { value: number; label: string };
  /** Show 95% CI whiskers when ciLow/ciHigh are present */
  showCI?: boolean;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

export default function BarChart({ data, baseline, showCI = false }: Props) {
  // sort descending by value (nulls last)
  const sorted = [...data].sort((a, b) => {
    if (a.value === null) return 1;
    if (b.value === null) return -1;
    return b.value - a.value;
  });

  return (
    <div className="bars">
      {sorted.map((d) => (
        <div className="bar-row" key={d.modelId}>
          <div className="label" title={d.label}>{d.label}</div>
          <div className="bar-track">
            {d.value !== null && (
              <div
                className="bar-fill"
                style={{
                  width: `${Math.max(0, Math.min(1, d.value)) * 100}%`,
                  background: d.color,
                  opacity: 0.85,
                }}
              />
            )}
            {showCI && d.ciLow !== undefined && d.ciHigh !== undefined && (
              <div
                className="ci-whisker"
                style={{
                  left: `${d.ciLow * 100}%`,
                  width: `${(d.ciHigh - d.ciLow) * 100}%`,
                }}
              />
            )}
            {baseline !== undefined && (
              <div
                className="baseline-line"
                style={{ left: `${baseline.value * 100}%` }}
                title={`${baseline.label}: ${pct(baseline.value)}`}
              />
            )}
          </div>
          <div className="value">{pct(d.value)}</div>
        </div>
      ))}
      {baseline !== undefined && (
        <div className="baseline-legend">
          {baseline.label}: {pct(baseline.value)}
        </div>
      )}
    </div>
  );
}

/** Helper to build BarDatum[] from a CI score map plus model metadata.
 *  Rows may contain non-score meta keys (e.g. n_queries) which are ignored. */
export function buildCIBars(
  models: ModelMeta[],
  scores: Record<string, unknown> | undefined
): BarDatum[] {
  return models.map((m) => {
    const raw = scores?.[m.id];
    const s =
      raw && typeof raw === 'object' && 'mean' in raw
        ? (raw as { mean: number; ci_low: number; ci_high: number })
        : null;
    return {
      modelId: m.id,
      label: m.display_name,
      color: m.color,
      value: s ? s.mean : null,
      ciLow: s?.ci_low,
      ciHigh: s?.ci_high,
    };
  });
}

/** Helper to build BarDatum[] from a plain score map.
 *  Rows may contain non-numeric meta keys which are ignored. */
export function buildPlainBars(
  models: ModelMeta[],
  scores: Record<string, unknown> | undefined
): BarDatum[] {
  return models.map((m) => {
    const raw = scores?.[m.id];
    const value = typeof raw === 'number' ? raw : null;
    return {
      modelId: m.id,
      label: m.display_name,
      color: m.color,
      value,
    };
  });
}
