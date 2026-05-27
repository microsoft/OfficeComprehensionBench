interface Props {
  active: 'domain' | 'fidelity';
  onChange: (track: 'domain' | 'fidelity') => void;
}

export default function TrackSelector({ active, onChange }: Props) {
  return (
    <div className="track-tabs" role="tablist" aria-label="Benchmark track">
      <button
        role="tab"
        aria-selected={active === 'domain'}
        className={active === 'domain' ? 'active' : ''}
        onClick={() => onChange('domain')}
      >
        Domain Q&amp;A
      </button>
      <button
        role="tab"
        aria-selected={active === 'fidelity'}
        className={active === 'fidelity' ? 'active' : ''}
        onClick={() => onChange('fidelity')}
      >
        File Fidelity Q&amp;A
      </button>
    </div>
  );
}
