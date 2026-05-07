import { useMemo } from 'react'
import type { OCBLeaderboardData } from '../../types/leaderboard'
import { MODEL_COLORS, ORG_COLORS } from '../../utils/scores'
import ModelRankingsBar from '../charts/ModelRankingsBar'
import { useHover } from '../../context/HoverContext'

interface ModelTableProps {
  data: OCBLeaderboardData
  onModelSelect: (modelId: string) => void
  selectedModelId: string | null
}

const PER_APP_TABS = [
  { key: 'word',       label: 'Word' },
  { key: 'powerpoint', label: 'PowerPoint' },
  { key: 'excel',      label: 'Excel' },
  { key: 'multifile',  label: 'MultiFile' },
] as const

export default function ModelTable({ data, onModelSelect, selectedModelId }: ModelTableProps) {
  const { hoveredModel, setHoveredModel } = useHover()

  const rows = useMemo(() => {
    return data.metadata.models
      .map(m => ({
        modelId:     m.id,
        displayName: m.display_name,
        org:         m.org,
        score:       data.overall.all_apps?.[m.id]?.percentage ?? 0,
      }))
      .sort((a, b) => b.score - a.score)
  }, [data])

  const maxScore = rows[0]?.score ?? 100

  return (
    <div className="space-y-6">

      {/* ── All Apps main chart ── */}
      <div>
        <p className="text-xs font-semibold mb-3" style={{ color: 'var(--text-muted)' }}>
          All Apps — combined overall score
        </p>

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
                onClick={() => onModelSelect(row.modelId)}
                className="flex items-center gap-4 px-4 py-3 cursor-pointer transition-all"
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

        <p className="text-xs mt-2 text-right italic" style={{ color: 'var(--text-muted)' }}>
          Click a row to inspect that model ↗
        </p>
      </div>

      {/* ── Per-app mini charts ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {PER_APP_TABS.map(tab => (
          <ModelRankingsBar
            key={tab.key}
            compact
            label={tab.label}
            scores={data.overall[tab.key] ?? {}}
            models={data.metadata.models}
            selectedModelId={selectedModelId}
            onModelSelect={onModelSelect}
          />
        ))}
      </div>

    </div>
  )
}
