import { scoreCls, fmtPct } from '../utils/scores'

interface ScoreCellProps {
  value?: number
  showN?: number
}

export default function ScoreCell({ value, showN }: ScoreCellProps) {
  const cls = scoreCls(value)
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold font-mono ${cls}`}
      title={showN !== undefined ? `n = ${showN}` : undefined}
    >
      {fmtPct(value)}
      {showN !== undefined && (
        <span className="opacity-50 font-normal text-[10px]">n={showN}</span>
      )}
    </span>
  )
}
