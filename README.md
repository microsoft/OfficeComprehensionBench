# OfficeComprehensionBenchmark (OCB) — Evaluation Toolkit

LLM-as-judge evaluation pipeline for scoring AI assistant responses to
document-grounded questions over Office files (Word, Excel,
PowerPoint). Supports single-model evaluation (Azure OpenAI GPT) and
multi-LLM majority voting (GPT + Gemini + Claude).

The benchmark itself — questions, reference answers, atomic assertion
rubrics, the URL manifest, and the redistributable subset of reference
files — is hosted on Hugging Face:

**https://huggingface.co/datasets/confanon/OfficeComprehensionBenchmark**

This repository hosts the evaluation prompts, judge scripts, and the
download/conversion utilities that materialize the URL-referenced
portion of the corpus into native Office formats.

## About the benchmark

OCB has two tracks:

- **File Fidelity Q&A** — structural and visual perception of document
  artifacts (text, tables, charts, formulas, formatting, embedded
  objects). 244 files, 922 queries.
- **Domain Q&A** — expert-level reasoning over real-world business
  documents across 12 industries. 124 files, 120 queries, 8,450 atomic
  assertions.

OCB is intended for **evaluation, not training**. It is not validated
for file formats outside `.docx` / `.xlsx` / `.pptx`, nor for
high-stakes deployment decisions in regulated domains on the basis of
OCB scores alone.

## Quick start

```bash
# 1. environment
conda create -n comp python=3.12 -y
conda activate comp
pip install -r requirements.txt

# 2. credentials
cp .env.example .env          # then fill in keys (see "Setup" below)
az login                      # for Azure OpenAI (DefaultAzureCredential)

# 3. download the reference document corpus
python download_and_convert_files.py --output-dir reference_files
# Some sources (auth-gated, dead links, format-conversion failures) will
# error out — see "Manual downloads" below.

# 4. generate the query NDJSON files from the Hugging Face dataset
python generate_query_ndjson.py
# Writes four files under Input/Query/:
#   OfficeBenchmark_DomainQnA.ndjson              (120 queries)
#   OfficeBenchmark_ExcelQnA_FileFidelity.ndjson  (277)
#   OfficeBenchmark_PPTQnA_FileFidelity.ndjson    (238)
#   OfficeBenchmark_WordQnA_FileFidelity.ndjson   (383)

# 5. run the bundled PPT sample end-to-end
./run_sample.sh               # macOS / Linux / WSL / Git Bash
.\run_sample.ps1              # Windows PowerShell
```

The sample scripts run `compete_response_processor.py` against
`Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson` and
`Input/Scrape/sample_conversations.ndjson` (2 PPT records), write
results under `Output/PPT_SampleRun/`, and run multi-LLM majority-voting
evaluation with `--max-concurrent 40`.

## Contents

### Evaluation engine
- `evaluation.py` — single-model evaluation engine, assertion scoring,
  batch evaluation with async concurrency, metrics aggregation.
- `multi_llm_evaluator.py` — multi-LLM judge with majority voting
  (GPT + Gemini + Claude), native async clients, cached Azure tokens.

### Prompt
- `eval_prompt.md` — assertion-based judge prompt used by both evaluators.

### Orchestration
- `compete_response_processor.py` — matches scrape responses to NDJSON
  queries, runs evaluation, writes a per-run output bundle.
- `run_sample.sh` / `run_sample.ps1` — turn-key sample run against the
  bundled PPT QnA query set + 2-record sample scrape.

### Data prep
- `download_and_convert_files.py` — downloads the reference document
  corpus from the OCB Hugging Face manifest
  (`data/ocb_source_urls.parquet`). PDF sources are converted to
  `docx`/`pptx` via Adobe PDF Services. HTML sources are rendered to
  PDF with headless Edge/Chrome and then converted via Adobe — there is
  no fallback path for HTML, so both `PDF_SERVICES_CLIENT_ID` /
  `PDF_SERVICES_CLIENT_SECRET` and an installed Microsoft Edge or
  Google Chrome are required. Use `-f <filename>` to process specific
  files (repeat or comma-separate for multiple). See "Manual downloads"
  below for files that cannot be fetched automatically.
- `generate_query_ndjson.py` — generates the per-track query NDJSON
  files in `Input/Query/` from the OCB Hugging Face Q&A parquet
  (`data/ocb_qna_data.parquet`). Splits the 1,018 queries into four
  files: Domain Q&A plus Excel/PPT/Word File Fidelity. Run with
  `python generate_query_ndjson.py` (override the source via
  `--parquet <url-or-path>` or the destination via `--output-dir`).

### Manual downloads

`download_and_convert_files.py` will not retrieve every reference
document successfully — expect a handful of failures from auth-gated
sources (e.g. SEC EDGAR without `SEC_USER_AGENT`), dead links, sites
that block scripted access, or PDF/HTML→Office conversion errors.

After the run, check `reference_files/_download_results.json` (and
`reference_files/_download_summary.txt`) for the per-file status. Any
entries marked as failed need to be fetched and converted manually into
`reference_files/` using the filename and target format listed there.
`possible_manual_download.csv` is provided as a reference example of
what such a list looks like — documents that cannot be fetched
automatically (auth, dead links, etc.); listed with source URL,
original format, and target format.

#### Excluded from the public release (May 07 update)

Three Excel files included in the original evaluation set are
**excluded from the public release** because their Kaggle source
licensing (CC BY-NC-SA 4.0) is incompatible with the dataset license:

- `winemag-data-130k-v2_sampled.csv`
- `Banking_Call_Data.csv`
- `brazilian_ecommerce_cleaned.csv`

The associated File Fidelity queries targeting these files are also
excluded. Reported benchmark numbers in the accompanying paper reflect
the full evaluation set including these files; to reproduce the full
evaluation, obtain the three datasets directly from Kaggle under the
original publishers' terms. Source URLs are listed in the URL manifest.

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

End-to-end against your own scrape directory (bash / Linux / macOS / WSL):
```bash
python compete_response_processor.py \
  --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson \
  --scrape-directory Input/Scrape \
  --evaluate --eval-majority-vote --max-concurrent 40
```

Single scrape file with custom output directory:
```bash
python compete_response_processor.py \
  --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson \
  --scrape-file Input/Scrape/sample_conversations.ndjson \
  --output-dir PPT_SampleRun \
  --evaluate --eval-majority-vote --max-concurrent 40
```

PowerShell equivalent (use backticks `` ` `` for line continuation, not `\`):
```powershell
python compete_response_processor.py `
  --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson `
  --scrape-file Input/Scrape/sample_conversations.ndjson `
  --output-dir PPT_SampleRun `
  --evaluate --eval-majority-vote --max-concurrent 40
```
Or keep everything on one line:
```powershell
python compete_response_processor.py --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson --scrape-file Input/Scrape/sample_conversations.ndjson --output-dir PPT_SampleRun --evaluate --eval-majority-vote --max-concurrent 40
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

## Citation

```bibtex
@misc{ocb2026,
  title  = {OfficeComprehensionBenchmark},
  author = {Anonymous},
  year   = {2026}
}
```

## License

- **Code in this repository**: MIT — see [LICENSE](LICENSE).
- **OCB dataset** (questions, reference answers, atomic assertions,
  and the redistributable subset of reference files hosted on Hugging
  Face): Community Data License Agreement – Permissive, Version 2.0
  ([CDLA-Permissive-2.0](https://cdla.dev/permissive-2-0/)). Per-source
  attribution and notice details are maintained in the `NOTICES.md`
  file on the Hugging Face dataset repository.
- **URL-referenced files** (downloaded by
  `download_and_convert_files.py` from third-party publishers): retain
  their original licenses. OCB does not assert a license over these
  files; users fetch them directly from the original publishers under
  those publishers' terms.
