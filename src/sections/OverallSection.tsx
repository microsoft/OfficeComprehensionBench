import type { OCBLeaderboardData } from '../types/leaderboard'
import ModelTable from '../components/tables/ModelTable'

interface OverallSectionProps {
  data: OCBLeaderboardData
  onModelSelect: (id: string) => void
  selectedModelId: string | null
}

export default function OverallSection({ data, onModelSelect, selectedModelId }: OverallSectionProps) {
  return (
    <div>
      <div className="mb-4">
        <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          Overall Leaderboard
        </h2>
        <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          Combined accuracy across Document QnA and File Fidelity scenarios, by file type.
          Click any row to view the full model breakdown.
        </p>
      </div>
      <ModelTable
        data={data}
        onModelSelect={onModelSelect}
        selectedModelId={selectedModelId}
      />
    </div>
  )
}
