# Run the evaluation pipeline against the bundled PPT sample (PowerShell).
#
# Inputs:
#   Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson  (bundled, 2 rows)
#   Input/Scrape/sample_conversations.ndjson                       (PPT-only sample, 2 rows)
#
# Prereqs:
#   1. conda activate comp
#   2. Copy-Item .env.example .env  and fill in keys
#   3. az login   (DefaultAzureCredential for Azure OpenAI)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$InputNdjson = "OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson"
$ScrapeFile  = "Input/Scrape/sample_conversations.ndjson"
$OutputDir   = "PPT_SampleRun"
$QueryPath   = Join-Path "Input/Query" $InputNdjson

if (-not (Test-Path -LiteralPath $QueryPath)) {
    Write-Error "Sample query NDJSON not found at $QueryPath (it is bundled in the repo)."
    exit 1
}

Write-Host "`n========== Sample run: PPT QnA + sample_conversations ==========" -ForegroundColor Cyan

python compete_response_processor.py `
    --input $InputNdjson `
    --scrape-file $ScrapeFile `
    --output-dir $OutputDir `
    --evaluate `
    --eval-majority-vote `
    --max-concurrent 40
if ($LASTEXITCODE -ne 0) { Write-Error "Sample run failed with exit code $LASTEXITCODE"; exit 1 }

Write-Host "`n========== Sample run completed: Output/$OutputDir ==========" -ForegroundColor Green
