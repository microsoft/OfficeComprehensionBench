import { useState, useEffect } from 'react'
import type { OCBLeaderboardData } from './types/leaderboard'
import { HoverProvider } from './context/HoverContext'
import Header from './components/Header'
import SummaryCards from './components/SummaryCards'
import ModelDetailPanel from './components/ModelDetailPanel'
import ModelTable from './components/tables/ModelTable'
import DomainQnASection from './sections/DomainQnASection'
import FileFidelitySection from './sections/FileFidelitySection'
import ComprehensionBySizeSection from './sections/ComprehensionBySizeSection'

const SECTIONS = [
  { id: 'domain-qna', label: 'Domain QnA' },
  { id: 'fidelity',   label: 'File Fidelity' },
  { id: 'rankings',   label: 'Combined' },
  { id: 'by-size',    label: 'By Size' },
]

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export default function App() {
  const [data, setData]               = useState<OCBLeaderboardData | null>(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [darkMode, setDarkMode]       = useState(() => {
    const saved = localStorage.getItem('ocb-dark')
    if (saved !== null) return saved === '1'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    localStorage.setItem('ocb-dark', darkMode ? '1' : '0')
  }, [darkMode])

  useEffect(() => {
    fetch('./data/leaderboard.json')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((d: OCBLeaderboardData) => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center"
         style={{ background: 'var(--bg-primary)' }}>
      <div className="text-center">
        <div className="w-10 h-10 border-4 rounded-full animate-spin mx-auto mb-4"
             style={{ borderColor: 'var(--border)', borderTopColor: 'var(--accent)' }}/>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Loading…</p>
      </div>
    </div>
  )

  if (error || !data) return (
    <div className="min-h-screen flex items-center justify-center"
         style={{ background: 'var(--bg-primary)' }}>
      <div className="card p-8 text-center max-w-sm">
        <div className="text-3xl mb-3">⚠️</div>
        <h2 className="font-bold mb-2" style={{ color: 'var(--text-primary)' }}>Failed to load</h2>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{error ?? 'Unknown error'}</p>
      </div>
    </div>
  )

  return (
    <HoverProvider>
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>

      {/* ── Sticky header with inline jump nav ── */}
      <Header
        benchmarkName={data.metadata.benchmark_name}
        version={data.metadata.version}
        lastUpdated={data.metadata.last_updated}
        darkMode={darkMode}
        onToggleDark={() => setDarkMode(d => !d)}
        sections={SECTIONS}
        onSectionClick={scrollTo}
      />

      {/* ── Page content ── */}
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 py-8 space-y-14">

        {/* ── Summary cards ── */}
        <SummaryCards data={data} />

        {/* ══ Section 1: Domain QnA ══ */}
        <section id="domain-qna">
          <SectionHeader
            number="01"
            title="Domain QnA Accuracy"
            description="How accurately each model answers questions drawn from documents across 13 industry domains."
          />
          <DomainQnASection data={data.domain_qna} models={data.metadata.models} />
        </section>

        {/* ══ Section 2: File Fidelity ══ */}
        <section id="fidelity">
          <SectionHeader
            number="02"
            title="File Fidelity"
            description="How accurately each model preserves document structure and features — tables, fonts, hyperlinks, charts, and more."
          />
          <FileFidelitySection data={data.file_fidelity} models={data.metadata.models} />
        </section>

        {/* ══ Section 3: Combined Rankings ══ */}
        <section id="rankings">
          <SectionHeader
            number="03"
            title="Combined"
            description="Combined score across Document QnA and File Fidelity, by file type. Click any row for the full model breakdown."
          />
          <ModelTable
            data={data}
            onModelSelect={id => setSelectedModel(prev => prev === id ? null : id)}
            selectedModelId={selectedModel}
          />
        </section>

        {/* ══ Section 4: Comprehension by Size ══ */}
        <section id="by-size">
          <SectionHeader
            number="04"
            title="Comprehension by Document Size"
            description="How document length (Small / Medium / Long) affects comprehension accuracy across models."
          />
          <ComprehensionBySizeSection
            data={data.comprehension_by_size}
            models={data.metadata.models}
          />
        </section>

      </div>

      {/* ── Footer ── */}
      <footer className="border-t mt-16 py-6"
              style={{ borderColor: 'var(--border)' }}>
        <div className="max-w-screen-xl mx-auto px-6 flex flex-col gap-3">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            © {new Date().getFullYear()} Microsoft Corporation. All rights reserved.
            Microsoft, Office, Word, PowerPoint, and Excel are registered trademarks of Microsoft Corporation.
          </span>
        </div>
      </footer>

      {/* ── Model detail panel ── */}
      {selectedModel && (
        <ModelDetailPanel
          modelId={selectedModel}
          data={data}
          onClose={() => setSelectedModel(null)}
        />
      )}
    </div>
    </HoverProvider>
  )
}

/* ── Small layout helpers ── */

function SectionHeader({ number, title, description }: {
  number: string; title: string; description: string
}) {
  return (
    <div className="mb-6 flex gap-5 items-start">
      <span className="text-3xl font-black leading-none mt-0.5 flex-shrink-0"
            style={{ color: 'var(--border-strong)', fontVariantNumeric: 'tabular-nums' }}>
        {number}
      </span>
      <div>
        <h2 className="text-xl font-bold leading-tight" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>{description}</p>
      </div>
    </div>
  )
}

function Divider() {
  return <hr style={{ borderColor: 'var(--border)', margin: 0 }} />
}
