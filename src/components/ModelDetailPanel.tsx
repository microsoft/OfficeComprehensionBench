import { useEffect } from 'react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts'
import type { OCBLeaderboardData, ModelInfo } from '../types/leaderboard'
import { MODEL_COLORS, FILE_TYPE_LABELS, fmtPct, scoreCls } from '../utils/scores'

interface ModelDetailPanelProps {
  modelId: string
  data: OCBLeaderboardData
  onClose: () => void
}

function SectionScore({ label, value }: { label: string; value?: number }) {
  const cls = scoreCls(value)
  return (
    <div className="flex items-center justify-between py-2 border-b"
         style={{ borderColor: 'var(--border)' }}>
      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span className={`px-2 py-0.5 rounded text-xs font-semibold font-mono ${cls}`}>
        {fmtPct(value)}
      </span>
    </div>
  )
}

export default function ModelDetailPanel({ modelId, data, onClose }: ModelDetailPanelProps) {
  const model: ModelInfo | undefined = data.metadata.models.find(m => m.id === modelId)

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  if (!model) return null

  const color = MODEL_COLORS[modelId] ?? '#0078D4'

  // Build radar data: per-file-type scores across overall, qna, fidelity
  const radarData = (['word', 'powerpoint', 'excel'] as const).map(ft => ({
    metric: FILE_TYPE_LABELS[ft],
    Overall:  data.overall[ft]?.[modelId]?.percentage,
    QnA:      data.domain_qna.overall[ft]?.[modelId]?.percentage,
    Fidelity: data.file_fidelity.overall[ft]?.[modelId]?.percentage,
  }))

  // Build domain bar chart data
  const domainData = Object.entries(data.domain_qna.by_domain)
    .map(([domain, scores]) => ({
      domain: domain.length > 28 ? domain.slice(0, 28) + '…' : domain,
      score: +(scores[modelId]?.percentage ?? 0).toFixed(1),
    }))
    .sort((a, b) => b.score - a.score)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        style={{ background: 'rgba(0,0,0,.4)' }}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className="fixed top-0 right-0 h-full z-50 overflow-y-auto"
        style={{
          width: 'min(520px, 95vw)',
          background: 'var(--bg-surface)',
          borderLeft: '1px solid var(--border)',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b"
             style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-1 h-10 rounded" style={{ background: color, flexShrink: 0 }} />
            <div className="min-w-0">
              <h2 className="font-bold text-base leading-tight truncate"
                  style={{ color: 'var(--text-primary)' }}>{model.display_name}</h2>
              <span className="text-xs font-medium" style={{ color }}>
                {model.org}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded flex items-center justify-center text-lg font-bold flex-shrink-0 transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent-light)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-6">

          {/* Overall scores */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-muted)' }}>Overall Scores</h3>
            <SectionScore label="All Apps (Overall)"       value={data.overall.all_apps?.[modelId]?.percentage} />
            <SectionScore label="Word"                     value={data.overall.word?.[modelId]?.percentage} />
            <SectionScore label="PowerPoint"               value={data.overall.powerpoint?.[modelId]?.percentage} />
            <SectionScore label="Excel"                    value={data.overall.excel?.[modelId]?.percentage} />
            <SectionScore label="MultiFile"                value={data.overall.multifile?.[modelId]?.percentage} />
          </div>

          {/* QnA vs Fidelity breakdown */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-muted)' }}>QnA vs Fidelity by File Type</h3>
            <div className="card p-3">
              <ResponsiveContainer width="100%" height={240}>
                <RadarChart data={radarData} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis
                    dataKey="metric"
                    tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
                  />
                  <Radar name="Overall"  dataKey="Overall"  stroke={color}          fill={color}          fillOpacity={0.15} />
                  <Radar name="QnA"      dataKey="QnA"      stroke="#10A37F"        fill="#10A37F"        fillOpacity={0.15} />
                  <Radar name="Fidelity" dataKey="Fidelity" stroke="#8764B8"        fill="#8764B8"        fillOpacity={0.15} />
                  <Tooltip
                    formatter={(v: number) => `${v?.toFixed(1)}%`}
                    contentStyle={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      fontSize: 11,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Domain QnA breakdown */}
          {domainData.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}>Domain QnA Breakdown</h3>
              <div className="card p-3">
                <ResponsiveContainer width="100%" height={domainData.length * 28 + 20}>
                  <BarChart
                    data={domainData}
                    layout="vertical"
                    margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
                    barCategoryGap="20%"
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border)" />
                    <YAxis
                      type="category"
                      dataKey="domain"
                      width={180}
                      tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <XAxis
                      type="number"
                      domain={[0, 100]}
                      tickFormatter={v => `${v}%`}
                      tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      formatter={(v: number) => [`${v.toFixed(1)}%`, 'Score']}
                      contentStyle={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border)',
                        fontSize: 11,
                      }}
                    />
                    <Bar dataKey="score" fill={color} radius={[0, 2, 2, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* QnA Detail */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-muted)' }}>QnA Scores</h3>
            <SectionScore label="All Apps"   value={data.domain_qna.overall.all_apps?.[modelId]?.percentage} />
            <SectionScore label="Word"       value={data.domain_qna.overall.word?.[modelId]?.percentage} />
            <SectionScore label="PowerPoint" value={data.domain_qna.overall.powerpoint?.[modelId]?.percentage} />
            <SectionScore label="Excel"      value={data.domain_qna.overall.excel?.[modelId]?.percentage} />
            <SectionScore label="MultiFile"  value={data.domain_qna.overall.multifile?.[modelId]?.percentage} />
          </div>

          {/* Fidelity Detail */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-muted)' }}>Fidelity Scores</h3>
            <SectionScore label="All Apps"   value={data.file_fidelity.overall.all_apps?.[modelId]?.percentage} />
            <SectionScore label="Word"       value={data.file_fidelity.overall.word?.[modelId]?.percentage} />
            <SectionScore label="PowerPoint" value={data.file_fidelity.overall.powerpoint?.[modelId]?.percentage} />
            <SectionScore label="Excel"      value={data.file_fidelity.overall.excel?.[modelId]?.percentage} />
          </div>

        </div>
      </div>
    </>
  )
}
