# OCB Leaderboard

The Office Comprehension Benchmark leaderboard site, built with Vite + React + TypeScript.

## Branch layout
- **`main`** — Benchmark source code (evaluation scripts, prompts, data pipeline).
- **`gh-pages`** — *(this branch)* Leaderboard UI source. A GitHub Actions workflow builds and deploys it to GitHub Pages on every push.

## Local development
```bash
npm install
npm run dev
```
The dev server fetches `public/data/leaderboard.json`. The canonical data file lives at `data/leaderboard.json`; the CI workflow copies it into `public/` before building.

## Data schema (v2)
See [data/leaderboard.json](./data/leaderboard.json). Two tracks:

### `domain_qna` — every score has 95% CI
- `main` — top-level chart with 3 models.
- `ablations.modes` + per-model entries — thinking-mode ablation per model.
- `by_industry` — one entry per industry (12 charts).
- `by_file_type` — `WXP` / `WX` / `WP` combinations.

### `file_fidelity` — plain point scores
- `human_baseline.{word,powerpoint,excel}` — dotted overlay value.
- For each app (`word`, `powerpoint`, `excel`):
  - `main` — 3-model overall.
  - `by_feature` — feature-level breakdown.
  - `by_size` — `small` / `medium` / `long` breakdown.

## Deployment
Push to `gh-pages` → GitHub Actions builds `dist/` and publishes it via the Pages deploy API. Configure your repository Pages source to **"GitHub Actions"** under Settings → Pages.
