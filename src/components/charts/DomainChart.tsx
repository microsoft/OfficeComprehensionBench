import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { ModelInfo, ModelScoreMap } from '../../types/leaderboard'
import { MODEL_COLORS } from '../../utils/scores'

interface DomainChartProps {
  byDomain: Record<string, ModelScoreMap>
  models: ModelInfo[]
  title?: string
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded shadow-lg p-3 text-xs min-w-[160px]"
         style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <p className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: p.color }} />
            <span style={{ color: 'var(--text-secondary)' }}>{p.name}</span>
          </span>
          <span className="font-mono font-semibold" style={{ color: 'var(--text-primary)' }}>
            {(p.value as number)?.toFixed(1)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export default function DomainChart({ byDomain, models, title }: DomainChartProps) {
  const chartData = useMemo(() =>
    Object.entries(byDomain).map(([domain, scores]) => {
      const entry: Record<string, string | number> = { domain }
      for (const m of models) {
        entry[m.id] = +(scores[m.id]?.percentage ?? 0).toFixed(2)
      }
      return entry
    }),
  [byDomain, models])

  const chartHeight = Math.max(300, chartData.length * 38 + 60)

  return (
    <div>
      {title && (
        <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          {title}
        </h3>
      )}
      <div className="card p-4" style={{ overflowX: 'auto' }}>
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 24, left: 0, bottom: 0 }}
            barGap={2}
            barCategoryGap="25%"
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={false}
                           stroke="var(--border)" />
            <YAxis
              type="category"
              dataKey="domain"
              width={220}
              tick={{ fontSize: 12, fill: 'var(--text-secondary)' }}
              tickLine={false}
              axisLine={false}
            />
            <XAxis
              type="number"
              domain={[0, 100]}
              tickFormatter={v => `${v}%`}
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--accent-light)' }} />
            <Legend
              wrapperStyle={{ fontSize: 11, paddingTop: 12 }}
              formatter={(value) => {
                const m = models.find(x => x.id === value)
                return <span style={{ color: 'var(--text-secondary)' }}>{m?.display_name ?? value}</span>
              }}
            />
            {models.map(m => (
              <Bar key={m.id} dataKey={m.id} name={m.id}
                   fill={MODEL_COLORS[m.id] ?? '#888'} radius={[0, 2, 2, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
