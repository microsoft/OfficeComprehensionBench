# Run the evaluation pipeline against the bundled PPT sample (PowerShell).
# Settings mirrored from run_fidelity_0430_all3models_round6.ps1.
#
# Inputs:
#   Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson
#   Input/Scrape/sample_conversations.ndjson  (PPT-only sample, 2 rows)
#
# Prereqs:
#   1. conda activate comp
#   2. Copy-Item .env.example .env  and fill in keys
#   3. az login   (DefaultAzureCredential for Azure OpenAI)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$InputNdjson = "OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson"
$ScrapeFile  = "Input/Scrape/sample_conversations.ndjson"
$OutputDir   = "PPT_0505_Sample_Round6_Eval1"

Write-Host "`n========== Sample run: PPT QnA + sample_conversations ==========" -ForegroundColor Cyan

python compete_tsv_response_processor.py `
    --input $InputNdjson `
    --tsv-file $ScrapeFile `
    --output-dir $OutputDir `
    --evaluate `
    --eval-majority-vote `
    --max-concurrent 40
if ($LASTEXITCODE -ne 0) { Write-Error "Sample run failed with exit code $LASTEXITCODE"; exit 1 }

Write-Host "`n========== Sample run completed: Output/$OutputDir ==========" -ForegroundColor Green
