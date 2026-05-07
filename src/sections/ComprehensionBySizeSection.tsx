import type { ComprehensionBySizeSection as SizeData, ModelInfo, SizeBreakdown } from '../types/leaderboard'
import { MODEL_COLORS } from '../utils/scores'
import { useHover } from '../context/HoverContext'

interface ComprehensionBySizeSectionProps {
  data: SizeData
  models: ModelInfo[]
}

const FILE_TYPE_TABS = [
  { key: 'word' as const,       label: 'Word' },
  { key: 'powerpoint' as const, label: 'PowerPoint' },
  { key: 'excel' as const,      label: 'Excel' },
]

const SIZE_GROUPS = [
  { key: 'small'  as const, label: 'Small' },
  { key: 'medium' as const, label: 'Medium' },
  { key: 'long'   as const, label: 'Long' },
]

/** One file-type card: three size groups, each with horizontal model bars */
function SizeBarChart({
  label,
  sizeData,
  models,
}: {
  label: string
  sizeData: SizeBreakdown
  models: ModelInfo[]
}) {
  const { hoveredModel, setHoveredModel } = useHover()

  // Global max across all sizes so bars are comparable within the card
  const allScores = SIZE_GROUPS.flatMap(sg =>
    models.map(m => sizeData[sg.key]?.[m.id]?.percentage ?? 0)
  )
  const maxScore = Math.max(...allScores, 1)

  return (
    <div
      className="rounded-xl overflow-hidden flex flex-col"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {/* Card header */}
      <div
        className="px-4 py-2.5 border-b"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface-2)' }}
      >
        <span className="text-xs font-bold" style={{ color: 'var(--text-secondary)' }}>
          {label}
        </span>
      </div>

      <div className="px-4 py-3 flex flex-col gap-4">
        {SIZE_GROUPS.map((sg, gi) => {
          const rows = models
            .map(m => ({
              modelId:     m.id,
              displayName: m.display_name,
              score:       sizeData[sg.key]?.[m.id]?.percentage ?? 0,
            }))
            .sort((a, b) => b.score - a.score)

          return (
            <div key={sg.key}>
              {/* Size label */}
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className="text-[10px] font-bold uppercase tracking-wider"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {sg.label}
                </span>
                {gi < SIZE_GROUPS.length - 1 && (
                  <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
                )}
              </div>

              {/* Model bars */}
              <div className="flex flex-col gap-1">
                {rows.map(row => {
                  const color     = MODEL_COLORS[row.modelId] ?? '#888'
                  const barPct    = (row.score / maxScore) * 100
                  const isHovered = hoveredModel === row.modelId
                  const dimmed    = hoveredModel !== null && !isHovered

                  return (
                    <div
                      key={row.modelId}
                      className="flex items-center gap-2 transition-opacity"
                      style={{ opacity: dimmed ? 0.2 : 1 }}
                      onMouseEnter={() => setHoveredModel(row.modelId)}
                      onMouseLeave={() => setHoveredModel(null)}
                    >
                      <div
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ background: color, opacity: isHovered ? 1 : 0.7 }}
                      />
                      <span
                        className="text-[10px] truncate flex-shrink-0"
                        style={{
                          width: 68,
                          color: isHovered ? 'var(--text-primary)' : 'var(--text-muted)',
                          fontWeight: isHovered ? 600 : 400,
                        }}
                        title={row.displayName}
                      >
                        {row.displayName}
                      </span>
                      <div
                        className="flex-1 rounded-full overflow-hidden"
                        style={{ height: 5, background: 'var(--bg-primary)' }}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${barPct}%`, background: color, opacity: isHovered ? 1 : 0.65 }}
                        />
                      </div>
                      <span
                        className="text-[10px] tabular-nums flex-shrink-0 text-right"
                        style={{
                          width: 32,
                          color: isHovered ? 'var(--text-primary)' : 'var(--text-muted)',
                          fontWeight: isHovered ? 700 : 400,
                        }}
                      >
                        {row.score > 0 ? `${row.score.toFixed(0)}%` : '—'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ComprehensionBySizeSection({ data, models }: ComprehensionBySizeSectionProps) {
  const { hoveredModel, setHoveredModel } = useHover()

  return (
    <div className="space-y-6">

      {/* Model legend */}
      <div className="flex flex-wrap gap-3">
        {models.map(m => (
          <div
            key={m.id}
            className="flex items-center gap-1.5 cursor-default transition-opacity"
            style={{ opacity: hoveredModel && hoveredModel !== m.id ? 0.3 : 1 }}
            onMouseEnter={() => setHoveredModel(m.id)}
            onMouseLeave={() => setHoveredModel(null)}
          >
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: MODEL_COLORS[m.id] ?? '#888' }} />
            <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
              {m.display_name}
            </span>
          </div>
        ))}
      </div>

      {/* 3 charts side by side */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {FILE_TYPE_TABS.map(tab => (
          <SizeBarChart
            key={tab.key}
            label={tab.label}
            sizeData={data[tab.key]}
            models={models}
          />
        ))}
      </div>

    </div>
  )
}
