import type { OCBLeaderboardData } from '../types/leaderboard'
import { topModel, fmtPct, countFeatures } from '../utils/scores'

interface SummaryCardsProps {
  data: OCBLeaderboardData
}

interface CardProps {
  icon: React.ReactNode
  label: string
  value: string
  sub: string
  accent: string
}

function Card({ icon, label, value, sub, accent }: CardProps) {
  return (
    <div className="card p-4 flex gap-3 items-start" style={{ borderTop: `3px solid ${accent}` }}>
      <div className="flex-shrink-0 w-9 h-9 rounded flex items-center justify-center text-white text-lg"
           style={{ background: accent }}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase tracking-wider mb-0.5"
             style={{ color: 'var(--text-muted)' }}>{label}</div>
        <div className="text-base font-bold leading-tight truncate"
             style={{ color: 'var(--text-primary)' }}>{value}</div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{sub}</div>
      </div>
    </div>
  )
}

export default function SummaryCards({ data }: SummaryCardsProps) {
  const models = data.metadata.models

  const topOverall = topModel(data.overall.all_apps, models)
  const topOverallScore = topOverall ? data.overall.all_apps[topOverall.id]?.percentage : undefined

  const topQnA = topModel(data.domain_qna.overall.all_apps, models)
  const topQnAScore = topQnA ? data.domain_qna.overall.all_apps[topQnA.id]?.percentage : undefined

  const topFidelity = topModel(data.file_fidelity.overall.all_apps, models)
  const topFidelityScore = topFidelity ? data.file_fidelity.overall.all_apps[topFidelity.id]?.percentage : undefined

  const totalFeatures = countFeatures(data.file_fidelity.by_feature)
  const totalDomains = Object.keys(data.domain_qna.by_domain).length

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
      <Card
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>}
        label="Top Overall"
        value={topOverall?.display_name ?? '—'}
        sub={topOverall ? `${fmtPct(topOverallScore)} · All Apps` : 'No data'}
        accent="#0078D4"
      />
      <Card
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/><path d="M8 13h8v1H8zm0 3h6v1H8z"/></svg>}
        label="Top QnA"
        value={topQnA?.display_name ?? '—'}
        sub={topQnA ? `${fmtPct(topQnAScore)} · Domain QnA` : 'No data'}
        accent="#107C10"
      />
      <Card
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>}
        label="Top Fidelity"
        value={topFidelity?.display_name ?? '—'}
        sub={topFidelity ? `${fmtPct(topFidelityScore)} · File Fidelity` : 'No data'}
        accent="#8764B8"
      />
      <Card
        icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 3c1.93 0 3.5 1.57 3.5 3.5S13.93 13 12 13s-3.5-1.57-3.5-3.5S10.07 6 12 6zm7 13H5v-.23c0-.62.28-1.2.76-1.58C7.47 15.82 9.64 15 12 15s4.53.82 6.24 2.19c.48.38.76.97.76 1.58V19z"/></svg>}
        label="Benchmark"
        value={`${models.length} Models`}
        sub={`${totalDomains} Domains · ${totalFeatures} Features`}
        accent="#C43501"
      />
    </div>
  )
}
