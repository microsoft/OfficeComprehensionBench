import type { ModelInfo, ModelScoreMap, FileTypeBreakdown } from '../types/leaderboard'

export const MODEL_COLORS: Record<string, string> = {
  work_copilot_gpt54_think_deeper: '#0078D4',
  web_copilot_gpt54_think_deeper:  '#00A2E8',
  claude_opus_46:                  '#CC7843',
  gpt54_think:                     '#10A37F',
  gemini_31_pro:                   '#EA4335',
}

export const FILE_TYPE_LABELS: Record<string, string> = {
  word:       'Word',
  powerpoint: 'PowerPoint',
  excel:      'Excel',
  multifile:  'MultiFile',
  all_apps:   'All Apps',
}

export const ORG_COLORS: Record<string, string> = {
  Microsoft: '#0078D4',
  Anthropic: '#CC7843',
  OpenAI:    '#10A37F',
  Google:    '#EA4335',
}

/** Return CSS class name for a score 0–100 */
export function scoreCls(pct?: number): string {
  if (pct === undefined || pct === null) return 'score-empty'
  if (pct >= 80) return 'score-high'
  if (pct >= 60) return 'score-good'
  if (pct >= 40) return 'score-mid'
  return 'score-low'
}

/** Format a percentage to display string */
export function fmtPct(pct?: number): string {
  if (pct === undefined || pct === null) return '—'
  return pct.toFixed(1) + '%'
}

/** Find the model with the highest score in a ModelScoreMap */
export function topModel(map: ModelScoreMap, models: ModelInfo[]): ModelInfo | null {
  let best: ModelInfo | null = null
  let bestScore = -Infinity
  for (const m of models) {
    const s = map[m.id]?.percentage
    if (s !== undefined && s > bestScore) {
      bestScore = s
      best = m
    }
  }
  return best
}

/** Get score for a specific model from a map */
export function getScore(map: ModelScoreMap, modelId: string): number | undefined {
  return map[modelId]?.percentage
}

/** Compute simple average of all non-null scores in a ModelScoreMap */
export function avgScore(map: ModelScoreMap): number {
  const vals = Object.values(map).map(s => s.percentage).filter(v => v !== undefined)
  if (!vals.length) return 0
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

/** Count total features across all file types in by_feature */
export function countFeatures(byFeature: Record<string, Record<string, ModelScoreMap>>): number {
  return Object.values(byFeature).reduce((sum, ft) => sum + Object.keys(ft).length, 0)
}

/** Get all-apps score for a model, falling back through sections */
export function getAllAppsScore(
  overall: FileTypeBreakdown,
  modelId: string,
): number | undefined {
  return overall.all_apps?.[modelId]?.percentage
}
