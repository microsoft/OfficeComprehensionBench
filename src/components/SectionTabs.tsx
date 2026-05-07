import type { TabId } from '../types/leaderboard'

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'domain-qna',    label: 'Domain QnA',             icon: '❓' },
  { id: 'file-fidelity', label: 'File Fidelity',          icon: '✓' },
  { id: 'overall',       label: 'Combined',               icon: '◈' },
  { id: 'by-size',       label: 'Comprehension by Size',  icon: '⊡' },
]

interface SectionTabsProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
}

export default function SectionTabs({ activeTab, onTabChange }: SectionTabsProps) {
  return (
    <div className="flex gap-0 border-b mb-5 overflow-x-auto"
         style={{ borderColor: 'var(--border)' }}>
      {TABS.map(tab => (
        <button
          key={tab.id}
          className={`tab-btn${activeTab === tab.id ? ' active' : ''}`}
          onClick={() => onTabChange(tab.id)}
        >
          <span className="mr-1.5 opacity-60 text-xs">{tab.icon}</span>
          {tab.label}
        </button>
      ))}
    </div>
  )
}
