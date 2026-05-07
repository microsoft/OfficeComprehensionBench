# Evaluation Toolkit

LLM-as-judge evaluation pipeline for scoring AI assistant responses to
document-grounded questions. Supports single-model evaluation
(Azure OpenAI GPT) and multi-LLM majority voting (GPT + Gemini + Claude).

## Quick start

```bash
# 1. environment
conda create -n comp python=3.12 -y
conda activate comp
pip install -r requirements.txt

# 2. credentials
cp .env.example .env          # then fill in keys (see "Setup" below)
az login                      # for Azure OpenAI (DefaultAzureCredential)

# 3. (optional) download the reference document corpus
python download_and_convert_files.py --output-dir reference_files

# 4. run the bundled PPT sample end-to-end
./run_sample.sh               # macOS / Linux / WSL / Git Bash
.\run_sample.ps1              # Windows PowerShell
```

The sample scripts run `compete_tsv_response_processor.py` against
`Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson`
and `Input/Scrape/sample_conversations.ndjson` (2 PPT records),
write results under `Output/PPT_0505_Sample_Round6_Eval1/`, and run
multi-LLM majority-voting evaluation with `--max-concurrent 40`.

## Contents

### Evaluation engine
- `evaluation.py` — single-model evaluation engine, assertion scoring,
  batch evaluation with async concurrency, metrics aggregation.
- `multi_llm_evaluator.py` — multi-LLM judge with majority voting
  (GPT + Gemini + Claude), native async clients, cached Azure tokens.

### Prompt
- `eval_prompt.md` — assertion-based judge prompt used by both evaluators.

### Orchestration
- `compete_tsv_response_processor.py` — matches scrape responses to NDJSON
  queries, runs evaluation, writes a per-run output bundle.
- `run_sample.sh` / `run_sample.ps1` — turn-key sample run against the
  bundled PPT QnA query set + 2-record sample scrape.

### Data prep
- `download_and_convert_files.py` — downloads the reference document
  corpus from public URLs / HuggingFace, converting PDFs and HTML to
  Office formats where needed.
- `files_source_url.json` — manifest of the 301 reference documents.
- `possible_manual_download.csv` — 25 documents that cannot be fetched
  automatically (auth, dead links, etc.); listed with source URL,
  original format, and target format.

### Post-processing
- `evaluate_results.py` — re-run evaluation against an existing results NDJSON.
- `generate_metrics_from_evaluation.py` — produce metrics JSON from an
  evaluation NDJSON.
- `visualize_categorized_metrics.py` — bar-chart ranking visualizations from
  metrics JSON.

## Data formats

Layout under `Input/`:
- `Input/Query/*.ndjson` — query sets (one JSON per line, see below). Released data is in these ndjson files
- `Input/Scrape/*.ndjson` — scrape responses (one JSON per line).
  `.tsv` is also accepted (slim header `filepath\tquery\tresponse`, or
  legacy 7-column raw scrape).

Input query NDJSON (one JSON per line):
```json
{"filepath": "doc.docx", "id": "1", "query": "question",
 "gold": ["Assertion 1", "Assertion 2"]}
```
`gold` may be a single string or a list of assertion strings. Extra
metadata fields (e.g. `original_format`, `feature`) are ignored.

Scrape NDJSON (one JSON per line):
```json
{"filepath": "doc.docx", "query": "What does ... ?", "response": "The model's answer ..."}
{"filepath": ["a.docx", "b.docx"], "query": "Compare ...", "response": "..."}
```
`filepath` may be a string or a list of filenames.

Results NDJSON (written by the orchestrator):
```json
{"id": "1", "filepath": "doc.docx", "query": "question", "gold": [...],
 "model": "chatgpt", "answer": "response", "processing_time": 2.34,
 "success": true, "error": null}
```

The evaluation NDJSON adds per-assertion scores and reasoning.

## Setup

Required environment variables (`.env`):

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint (required). |
| `AZURE_OPENAI_API_VERSION` | Optional; defaults to `2025-03-01-preview`. |
| `GEMINI_API_KEY` | Required for `--eval-majority-vote`. |
| `ANTHROPIC_API_KEY` | Required for `--eval-majority-vote`. |
| `PDF_SERVICES_CLIENT_ID` / `PDF_SERVICES_CLIENT_SECRET` | Adobe PDF Services, required for PDF→DOCX/PPTX in `download_and_convert_files.py`. |
| `SEC_USER_AGENT` | Required only when downloading SEC EDGAR documents. |
| `HF_TOKEN` | Optional; only needed if the HuggingFace dataset is gated. |

Azure auth uses `DefaultAzureCredential`: run `az login`, or set
`AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID`.

Values in `.env` override any pre-existing shell / user-level env vars
(`load_dotenv(override=True)`), so a stale `AZURE_OPENAI_ENDPOINT` in
your User scope will not silently take precedence.

## Usage

Bundled sample (PPT, 2 records, multi-LLM majority voting):
```bash
./run_sample.sh        # or .\run_sample.ps1 on Windows
```

End-to-end against your own scrape directory:
```bash
python compete_tsv_response_processor.py \
  --input OfficeBenchmark_DomainQnA_0505_NoWS_NoCl_NoFC.ndjson \
  --scrape-directory Input/Scrape \
  --evaluate --eval-majority-vote --max-concurrent 40
```

Single scrape file with custom output directory:
```bash
python compete_tsv_response_processor.py \
  --input OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson \
  --tsv-file Input/Scrape/my_scrape.ndjson \
  --output-dir PPT_MyRun \
  --evaluate
```

Re-evaluate existing results:
```bash
python evaluate_results.py --input Output/run/results.ndjson
```

Useful flags:
- `--evaluate` — run evaluation after matching (default on).
- `--eval-majority-vote` — multi-LLM majority voting (GPT + Gemini + Claude).
- `--max-concurrent N` — concurrent evaluations (default 3).
- `--output-dir NAME` — explicit folder under `Output/`.
- `--limit N` — process only the first `N` queries (smoke testing).

## Models

Default judges (override via `--eval-gpt-model`, `--eval-gemini-model`,
`--eval-claude-model`):

- GPT-5.4 (Azure OpenAI, `responses.create`, low reasoning effort)
- Gemini 3.1 Pro Preview (`gemini-3.1-pro-preview`)
- Claude Opus 4.6 (`claude-opus-4-6`)

The single-model default is GPT-5.4. Majority voting requires all three
API keys.

## License

MIT — see `LICENSE`.
