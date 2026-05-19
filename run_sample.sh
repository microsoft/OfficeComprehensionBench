#!/usr/bin/env bash
# Run the evaluation pipeline against the bundled PPT sample.
#
# Inputs:
#   Input/Query/OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson  (bundled, 2 rows)
#   Input/Scrape/sample_conversations.ndjson                       (PPT-only sample, 2 rows)
#
# Prereqs:
#   1. conda activate comp  (or any Python 3.12 env with requirements.txt installed)
#   2. cp .env.example .env  and fill in keys
#   3. az login              (DefaultAzureCredential)

set -euo pipefail

cd "$(dirname "$0")"

INPUT_NDJSON="OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson"
SCRAPE_FILE="Input/Scrape/sample_conversations.ndjson"
OUTPUT_DIR="PPT_SampleRun"
QUERY_PATH="Input/Query/$INPUT_NDJSON"

if [ ! -f "$QUERY_PATH" ]; then
    echo "Sample query NDJSON not found at $QUERY_PATH (it is bundled in the repo)." >&2
    exit 1
fi

echo "========== Sample run: PPT QnA + sample_conversations =========="

python compete_response_processor.py \
    --input "$INPUT_NDJSON" \
    --scrape-file "$SCRAPE_FILE" \
    --output-dir "$OUTPUT_DIR" \
    --evaluate \
    --eval-majority-vote \
    --max-concurrent 40

echo "========== Sample run completed: Output/$OUTPUT_DIR =========="
