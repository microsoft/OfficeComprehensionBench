import { useEffect, useState } from 'react';
import type { Leaderboard } from './types/leaderboard';
import TrackSelector from './components/TrackSelector';
import DomainQnASection from './sections/DomainQnASection';
import FileFidelitySection from './sections/FileFidelitySection';

type Track = 'domain' | 'fidelity';

export default function App() {
  const [data, setData] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [track, setTrack] = useState<Track>('domain');

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/leaderboard.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="notice">Failed to load leaderboard: {error}</div>;
  if (!data) return <div className="notice">Loading…</div>;

  return (
    <>
      <header className="app-header">
        <div className="container">
          <div className="ms-brand">
            <img src={`${import.meta.env.BASE_URL}microsoft-logo.svg`} alt="Microsoft" width="20" height="20" />
            <span>Microsoft</span>
          </div>
          <h1>{data.metadata.benchmark_name}</h1>
        </div>
      </header>

      <main className="container">
        <TrackSelector active={track} onChange={setTrack} />
        {track === 'domain' ? (
          <DomainQnASection data={data} />
        ) : (
          <FileFidelitySection data={data} />
        )}
      </main>
    </>
  );
}
