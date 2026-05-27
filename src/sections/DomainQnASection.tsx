import type { Leaderboard, AblationMode, CIScore } from '../types/leaderboard';
import BarChart, { buildCIBars } from '../components/BarChart';

interface Props {
  data: Leaderboard;
}

export default function DomainQnASection({ data }: Props) {
  const { metadata, domain_qna } = data;
  const models = metadata.models;

  // Ablation chart configs — read per-model mode lists from JSON
  const ablations = domain_qna.ablations as unknown as Record<string, unknown>;
  const ablationCharts: { modelId: string; title: string; modes: AblationMode[] }[] = [];
  if (ablations.gpt55_modes) {
    ablationCharts.push({
      modelId: 'gpt55_think',
      title: 'GPT 5.5 — thinking-mode ablation',
      modes: ablations.gpt55_modes as AblationMode[],
    });
  }
  if (ablations.claude47_modes) {
    ablationCharts.push({
      modelId: 'claude_opus_47',
      title: 'Claude Opus 4.7 — thinking-mode ablation',
      modes: ablations.claude47_modes as AblationMode[],
    });
  }

  return (
    <>
      {/* ----- Main accuracy ----- */}
      <div className="section-title">Overall Accuracy</div>
      <div className="card">
        <h3>Main accuracy — all three models</h3>
        <div className="subtitle">Bars show point estimate; black whiskers show 95% confidence interval.</div>
        <BarChart data={buildCIBars(models, domain_qna.main)} showCI />
      </div>

      {/* ----- Ablations ----- */}
      <div className="section-title">Thinking-Mode Ablations</div>
      <div className="grid cols-2">
        {ablationCharts.map((cfg) => {
          const model = models.find((m) => m.id === cfg.modelId);
          if (!model) return null;
          const modelScores = (ablations[cfg.modelId] ?? {}) as Record<string, CIScore>;
          const bars = cfg.modes
            .filter((mode) => modelScores[mode.id])
            .map((mode) => ({
              modelId: mode.id,
              label: mode.label,
              color: model.color,
              value: modelScores[mode.id].mean,
              ciLow: modelScores[mode.id].ci_low,
              ciHigh: modelScores[mode.id].ci_high,
            }));
          return (
            <div className="card" key={cfg.modelId}>
              <h3>{cfg.title}</h3>
              <BarChart data={bars} showCI />
            </div>
          );
        })}
      </div>

      {/* ----- Industry breakdown ----- */}
      <div className="section-title">Accuracy by Industry</div>
      <div className="grid cols-3">
        {metadata.industries.map((ind) => (
          <div className="card" key={ind}>
            <h3>{ind}</h3>
            <BarChart data={buildCIBars(models, domain_qna.by_industry[ind] ?? {})} showCI />
          </div>
        ))}
      </div>

      {/* ----- File-type combos ----- */}
      <div className="section-title">Accuracy by File-Type Combination</div>
      <div className="grid cols-3">
        {metadata.file_type_combos.map((combo) => (
          <div className="card" key={combo.id}>
            <h3>{combo.id}</h3>
            <div className="subtitle">{combo.label}</div>
            <BarChart data={buildCIBars(models, domain_qna.by_file_type[combo.id] ?? {})} showCI />
          </div>
        ))}
      </div>
    </>
  );
}
