import type { Leaderboard, FidelityAppData } from '../types/leaderboard';
import BarChart, { buildPlainBars } from '../components/BarChart';
import HeatMap from '../components/HeatMap';

interface Props {
  data: Leaderboard;
}

const APP_LABELS: Record<string, string> = {
  word: 'Word',
  powerpoint: 'PowerPoint',
  excel: 'Excel',
};

const SIZE_ORDER = ['small', 'medium', 'long'];

export default function FileFidelitySection({ data }: Props) {
  const { metadata, file_fidelity } = data;
  const models = metadata.models;

  const renderApp = (app: string) => {
    const appData = (file_fidelity as unknown as Record<string, FidelityAppData>)[app];
    if (!appData) return null;

    const baseline = file_fidelity.human_baseline[app];
    const mainScores: Record<string, number> = {};
    for (const id of Object.keys(appData.main)) {
      mainScores[id] = appData.main[id].score;
    }

    // Sort size buckets in canonical order
    const sizeEntries = appData.by_size
      ? Object.entries(appData.by_size).sort(
          ([a], [b]) => SIZE_ORDER.indexOf(a) - SIZE_ORDER.indexOf(b)
        )
      : [];

    return (
      <div key={app}>
        <div className="section-title">{APP_LABELS[app]}</div>

        <div className="card">
          <h3>{APP_LABELS[app]} — overall accuracy</h3>
          <div className="subtitle">Dashed line shows human Q&amp;A baseline.</div>
          <BarChart
            data={buildPlainBars(models, mainScores)}
            baseline={baseline !== undefined ? { value: baseline, label: 'Human baseline' } : undefined}
          />
        </div>

        <div className="card">
          <h3>{APP_LABELS[app]} — accuracy by feature</h3>
          <HeatMap columns={appData.by_feature} models={models} sortBy="claude_opus_47" />
        </div>

        {sizeEntries.length > 0 && (
          <div className="card">
            <h3>{APP_LABELS[app]} — accuracy by document size</h3>
            <div className="bars">
              {sizeEntries.map(([size, row]) => (
                <div key={size} style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, margin: '6px 0 2px', textTransform: 'capitalize' }}>
                    {size}
                  </div>
                  <BarChart data={buildPlainBars(models, row as Record<string, number | null | undefined>)} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return <>{metadata.fidelity_apps.map(renderApp)}</>;
}
