import { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { ModelInfo, SizeBreakdown } from '../../types/leaderboard'
import { MODEL_COLORS, FILE_TYPE_LABELS } from '../../utils/scores'

interface SizeChartProps {
  sizeData: SizeBreakdown
  models: ModelInfo[]
  fileType: string
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded shadow-lg p-3 text-xs min-w-[160px]"
         style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <p className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>{label} Documents</p>
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

export default function SizeChart({ sizeData, models, fileType }: SizeChartProps) {
  const chartData = useMemo(() => {
    const sizes: { key: 'small' | 'medium' | 'long'; label: string }[] = [
      { key: 'small',  label: 'Small' },
      { key: 'medium', label: 'Medium' },
      { key: 'long',   label: 'Long' },
    ]
    return sizes.map(({ key, label }) => {
      const entry: Record<string, string | number> = { size: label }
      for (const m of models) {
        entry[m.id] = +(sizeData[key]?.[m.id]?.percentage ?? 0).toFixed(2)
      }
      return entry
    })
  }, [sizeData, models])

  const hasData = Object.values(sizeData).some(m => Object.keys(m).length > 0)

  if (!hasData) {
    return (
      <div className="card p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
        No size breakdown data available for {FILE_TYPE_LABELS[fileType] ?? fileType}.
      </div>
    )
  }

  return (
    <div className="card p-4">
      <ResponsiveContainer width="100%" height={320}>
        <BarChart
          data={chartData}
          margin={{ top: 10, right: 24, left: 0, bottom: 0 }}
          barGap={3}
          barCategoryGap="35%"
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="size"
            tick={{ fontSize: 13, fill: 'var(--text-secondary)', fontWeight: 600 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
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
                 fill={MODEL_COLORS[m.id] ?? '#888'} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
