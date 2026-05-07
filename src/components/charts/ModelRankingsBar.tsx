import type { ModelScoreMap, ModelInfo } from '../../types/leaderboard'
import { MODEL_COLORS, ORG_COLORS } from '../../utils/scores'
import { useHover } from '../../context/HoverContext'

interface ModelRankingsBarProps {
  scores: ModelScoreMap
  models: ModelInfo[]
  label?: string
  compact?: boolean
  selectedModelId?: string | null
  onModelSelect?: (id: string) => void
}

export default function ModelRankingsBar({
  scores,
  models,
  label,
  compact = false,
  selectedModelId,
  onModelSelect,
}: ModelRankingsBarProps) {
  const { hoveredModel, setHoveredModel } = useHover()

  const rows = models
    .map(m => ({
      modelId:     m.id,
      displayName: m.display_name,
      org:         m.org,
      score:       scores[m.id]?.percentage ?? 0,
    }))
    .sort((a, b) => b.score - a.score)

  const maxScore = rows[0]?.score ?? 100

  if (compact) {
    return (
      <div
        className="rounded-xl p-4 flex flex-col gap-2"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        {label && (
          <p className="text-xs font-bold mb-1" style={{ color: 'var(--text-secondary)' }}>
            {label}
          </p>
        )}
        {rows.map(row => {
          const color      = MODEL_COLORS[row.modelId] ?? '#888'
          const barPct     = maxScore > 0 ? (row.score / maxScore) * 100 : 0
          const isSelected = selectedModelId === row.modelId
          const isHovered  = hoveredModel === row.modelId
          const dimmed     = hoveredModel !== null && !isHovered

          return (
            <div
              key={row.modelId}
              onClick={() => onModelSelect?.(row.modelId)}
              className={`flex items-center gap-2 rounded px-1.5 py-0.5 -mx-1.5 transition-all${onModelSelect ? ' cursor-pointer' : ''}`}
              style={{
                background: isSelected ? 'var(--accent-light)' : 'transparent',
                opacity: dimmed ? 0.25 : 1,
              }}
              onMouseEnter={() => setHoveredModel(row.modelId)}
              onMouseLeave={() => setHoveredModel(null)}
            >
              <span
                className="text-[11px] truncate flex-shrink-0"
                style={{
                  width: 72,
                  color: isHovered ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: isHovered ? 600 : 400,
                }}
                title={row.displayName}
              >
                {row.displayName}
              </span>
              <div
                className="flex-1 rounded-full overflow-hidden"
                style={{ height: 6, background: 'var(--bg-primary)' }}
              >
                <div
                  className="h-full rounded-full"
                  style={{ width: `${barPct}%`, background: color, opacity: isHovered ? 1 : 0.7 }}
                />
              </div>
              <span
                className="text-[11px] tabular-nums flex-shrink-0 text-right"
                style={{
                  width: 38,
                  color: isHovered ? 'var(--text-primary)' : 'var(--text-muted)',
                  fontWeight: isHovered ? 700 : 400,
                }}
              >
                {row.score > 0 ? `${row.score.toFixed(1)}%` : '—'}
              </span>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {rows.map((row, i) => {
        const rank       = i + 1
        const color      = MODEL_COLORS[row.modelId] ?? '#888'
        const orgColor   = ORG_COLORS[row.org] ?? '#888'
        const barPct     = maxScore > 0 ? (row.score / maxScore) * 100 : 0
        const isSelected = selectedModelId === row.modelId
        const isHovered  = hoveredModel === row.modelId
        const dimmed     = hoveredModel !== null && !isHovered

        return (
          <div
            key={row.modelId}
            onClick={() => onModelSelect?.(row.modelId)}
            className={`flex items-center gap-4 px-4 py-3 transition-all${onModelSelect ? ' cursor-pointer' : ''}`}
            style={{
              background: isSelected ? 'var(--accent-light)' : undefined,
              opacity: dimmed ? 0.35 : 1,
            }}
            onMouseEnter={() => setHoveredModel(row.modelId)}
            onMouseLeave={() => setHoveredModel(null)}
          >
            <span
              className="text-xs font-black w-6 text-center flex-shrink-0 tabular-nums"
              style={{
                color: rank === 1 ? '#F59E0B'
                     : rank === 2 ? '#94A3B8'
                     : rank === 3 ? '#CD7F32'
                     : 'var(--text-muted)',
              }}
            >
              {rank}
            </span>
            <div className="w-1 h-9 rounded-full flex-shrink-0" style={{ background: color }} />
            <div className="w-52 flex-shrink-0 min-w-0">
              <div className="font-semibold text-sm leading-tight truncate"
                   style={{ color: 'var(--text-primary)' }}>
                {row.displayName}
              </div>
              <div className="text-[11px] font-medium mt-0.5" style={{ color: orgColor }}>
                {row.org}
              </div>
            </div>
            <div className="flex-1 flex items-center gap-3 min-w-0">
              <div
                className="flex-1 rounded-full overflow-hidden"
                style={{ height: 10, background: 'var(--bg-primary)' }}
              >
                <div
                  className="h-full rounded-full"
                  style={{ width: `${barPct}%`, background: color, opacity: 0.85 }}
                />
              </div>
              <span
                className="text-sm font-bold tabular-nums flex-shrink-0 w-14 text-right"
                style={{ color: 'var(--text-primary)' }}
              >
                {row.score > 0 ? `${row.score.toFixed(1)}%` : '—'}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
