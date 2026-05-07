#!/usr/bin/env bash
# Run the evaluation pipeline against the bundled PPT sample.
# Settings mirrored from run_fidelity_0430_all3models_round6.ps1.
#
# Inputs:
#   Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson
#   Input/Scrape/sample_conversations.ndjson  (PPT-only sample, 2 rows)
#
# Prereqs:
#   1. conda activate comp  (or any Python 3.12 env with requirements.txt installed)
#   2. cp .env.example .env  and fill in keys
#   3. az login              (DefaultAzureCredential)

set -euo pipefail

cd "$(dirname "$0")"

INPUT_NDJSON="OfficeBenchmark_PPTQnA_FileFidelity_0505_NoWS_NoCl_NoFC.ndjson"
SCRAPE_FILE="Input/Scrape/sample_conversations.ndjson"
OUTPUT_DIR="PPT_0505_Sample_Round6_Eval1"

echo "========== Sample run: PPT QnA + sample_conversations =========="

python compete_tsv_response_processor.py \
    --input "$INPUT_NDJSON" \
    --tsv-file "$SCRAPE_FILE" \
    --output-dir "$OUTPUT_DIR" \
    --evaluate \
    --eval-majority-vote \
    --max-concurrent 40

echo "========== Sample run completed: Output/$OUTPUT_DIR =========="
