import { useState } from 'react'
import type { DomainQnASection as DomainQnAData, ModelInfo, FileTypeKey, ModelScoreMap } from '../types/leaderboard'
import ModelRankingsBar from '../components/charts/ModelRankingsBar'
import { MODEL_COLORS } from '../utils/scores'
import { useHover } from '../context/HoverContext'

interface DomainQnASectionProps {
  data: DomainQnAData
  models: ModelInfo[]
}

const FILE_TYPE_TABS: { key: FileTypeKey; label: string }[] = [
  { key: 'all_apps',   label: 'All Apps' },
  { key: 'word',       label: 'Word' },
  { key: 'powerpoint', label: 'PowerPoint' },
  { key: 'excel',      label: 'Excel' },
  { key: 'multifile',  label: 'MultiFile' },
]

function pillStyle(isActive: boolean) {
  return isActive
    ? { background: 'var(--accent)', color: '#fff' }
    : { background: 'var(--bg-surface-2)', color: 'var(--text-secondary)' }
}

/** Single domain card — compact bars with cross-chart hover sync via context */
function DomainCard({
  domain,
  scores,
  models,
}: {
  domain: string
  scores: ModelScoreMap
  models: ModelInfo[]
}) {
  const { hoveredModel, setHoveredModel } = useHover()

  const rows = models
    .map(m => ({ modelId: m.id, displayName: m.display_name, score: scores[m.id]?.percentage ?? 0 }))
    .sort((a, b) => b.score - a.score)

  const maxScore = rows[0]?.score ?? 100
  const anyHovered = hoveredModel !== null

  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-1.5"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <p
        className="text-[11px] font-bold mb-1 truncate"
        style={{ color: 'var(--text-secondary)' }}
        title={domain}
      >
        {domain}
      </p>

      {rows.map(row => {
        const color      = MODEL_COLORS[row.modelId] ?? '#888'
        const barPct     = maxScore > 0 ? (row.score / maxScore) * 100 : 0
        const isHovered  = hoveredModel === row.modelId
        const dimmed     = anyHovered && !isHovered

        return (
          <div
            key={row.modelId}
            className="flex items-center gap-2 transition-opacity"
            style={{ opacity: dimmed ? 0.2 : 1, cursor: 'default' }}
            onMouseEnter={() => setHoveredModel(row.modelId)}
            onMouseLeave={() => setHoveredModel(null)}
          >
            {/* Color dot */}
            <div
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: color, opacity: isHovered ? 1 : 0.7 }}
            />

            {/* Model name */}
            <span
              className="text-[10px] truncate flex-shrink-0"
              style={{
                width: 64,
                color: isHovered ? 'var(--text-primary)' : 'var(--text-muted)',
                fontWeight: isHovered ? 600 : 400,
              }}
              title={row.displayName}
            >
              {row.displayName}
            </span>

            {/* Bar */}
            <div
              className="flex-1 rounded-full overflow-hidden"
              style={{ height: 5, background: 'var(--bg-primary)' }}
            >
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${barPct}%`,
                  background: color,
                  opacity: isHovered ? 1 : 0.65,
                }}
              />
            </div>

            {/* Score */}
            <span
              className="text-[10px] tabular-nums flex-shrink-0 text-right"
              style={{
                width: 30,
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
  )
}

export default function DomainQnASection({ data, models }: DomainQnASectionProps) {
  const [fileType, setFileType] = useState<FileTypeKey>('all_apps')
  const { hoveredModel, setHoveredModel } = useHover()

  const byDomain = fileType === 'all_apps'
    ? data.by_domain
    : (data.by_file_type_and_domain[fileType] ?? {})

  const domains = Object.keys(byDomain)
  const hasData = domains.length > 0

  return (
    <div className="space-y-8">

      {/* ── Overall QnA ranking chart ── */}
      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
            Overall Domain QnA accuracy — all apps
          </h3>
          <ModelRankingsBar
            scores={data.overall.all_apps ?? {}}
            models={models}
          />
        </div>

        {/* Per-app mini charts */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {(['word', 'powerpoint', 'excel', 'multifile'] as const).map(key => (
            <ModelRankingsBar
              key={key}
              compact
              label={{ word: 'Word', powerpoint: 'PowerPoint', excel: 'Excel', multifile: 'MultiFile' }[key]}
              scores={data.overall[key] ?? {}}
              models={models}
            />
          ))}
        </div>
      </div>

      {/* ── Per-domain grid ── */}
      <div>
        <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            Accuracy by industry domain
          </h3>

          {/* File type pills */}
          <div
            className="flex gap-1 p-1 rounded"
            style={{ background: 'var(--bg-surface-2)', border: '1px solid var(--border)' }}
          >
            {FILE_TYPE_TABS.map(tab => (
              <button
                key={tab.key}
                onClick={() => setFileType(tab.key)}
                className="px-3 py-1 text-xs font-medium rounded transition-all"
                style={pillStyle(fileType === tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Model legend / hover hint */}
        <div className="flex flex-wrap gap-3 mb-4">
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

        {!hasData ? (
          <div className="card p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            No domain breakdown data for{' '}
            {FILE_TYPE_TABS.find(t => t.key === fileType)?.label ?? fileType}.
            {fileType !== 'all_apps' && ' Try "All Apps".'}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {domains.map(domain => (
              <DomainCard
                key={domain}
                domain={domain}
                scores={byDomain[domain]}
                models={models}
              />
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
