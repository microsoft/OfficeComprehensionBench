interface NavSection { id: string; label: string }

interface HeaderProps {
  benchmarkName: string
  version: string
  lastUpdated: string
  darkMode: boolean
  onToggleDark: () => void
  sections?: NavSection[]
  onSectionClick?: (id: string) => void
}

export default function Header({
  benchmarkName, version, lastUpdated,
  darkMode, onToggleDark,
  sections = [], onSectionClick,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-30"
            style={{ background: 'var(--bg-header)' }}>
      {/* Top bar */}
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

        {/* Logo + title */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Microsoft logo */}
          <img
            src="./Microsoft-logo_rgb_c-gray.png"
            alt="Microsoft"
            className="flex-shrink-0"
            style={{ height: 60, width: 'auto' }}
          />

          {/* Divider */}
          <div className="flex-shrink-0 w-px h-4" style={{ background: 'var(--border-strong)' }} />

          {/* Benchmark name */}
          <span className="text-sm truncate" style={{ color: 'var(--text-secondary)' }}>
            {benchmarkName}
          </span>
        </div>

        {/* Right: dark toggle */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <button
            onClick={onToggleDark}
            aria-label="Toggle dark mode"
            className="w-7 h-7 rounded flex items-center justify-center transition-colors"
            style={{ background: 'var(--bg-surface-2)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--border)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-surface-2)')}
          >
            {darkMode
              ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="4"/><path d="M12 0v3M12 21v3M0 12h3M21 12h3M3.5 3.5l2.1 2.1M18.4 18.4l2.1 2.1M3.5 20.5l2.1-2.1M18.4 5.6l2.1-2.1"/></svg>
              : <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
            }
          </button>
        </div>
      </div>

    </header>
  )
}
