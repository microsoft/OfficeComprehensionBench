#!/usr/bin/env python3
"""
Generate Metrics from Evaluation Files

This script regenerates *_metrics.json files from existing *_evaluation.ndjson files.
Useful when you have evaluation results but need to recalculate or update metrics.

Usage:
    # Process specific evaluation file
    python generate_metrics_from_evaluation.py --input Output/Word_0905/Word_0905_evaluation.ndjson
    
    # Auto-discover and process all evaluation files
    python generate_metrics_from_evaluation.py
    
    # Process all evaluation files in a directory
    python generate_metrics_from_evaluation.py --input Output
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
import os

from evaluation import (
    EvaluationResult,
    calculate_categorized_accuracy_metrics,
    print_accuracy_report,
    save_categorized_metrics
)


def load_evaluation_results(ndjson_path: str) -> List[EvaluationResult]:
    """Load evaluation results from NDJSON file."""
    evaluation_results = []
    
    with open(ndjson_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                
                # Convert dict to EvaluationResult object
                eval_result = EvaluationResult(
                    id=data['id'],
                    criteria=data['criteria'],
                    rationale=data['rationale'],
                    score=data['score'],
                    evaluation_success=data['evaluation_success'],
                    evaluation_error=data.get('evaluation_error'),
                    total_assertions=data.get('total_assertions'),
                    passed_assertions=data.get('passed_assertions'),
                    assertion_results=data.get('assertion_results'),
                )
                evaluation_results.append(eval_result)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num}: {e}")
                continue
            except KeyError as e:
                print(f"Warning: Missing required field on line {line_num}: {e}")
                continue
    
    return evaluation_results


def load_processing_outputs_from_results(results_file: str) -> List[Dict[str, Any]]:
    """Load processing outputs from results.ndjson file (to get category metadata)."""
    outputs = []
    
    if not os.path.exists(results_file):
        print(f"Warning: Results file not found: {results_file}")
        return outputs
    
    with open(results_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                outputs.append(data)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num} in results file: {e}")
                continue
    
    return outputs


def find_evaluation_files(input_path: str = None) -> list:
    """Find evaluation files to process."""
    files = []
    
    if input_path and os.path.exists(input_path):
        if os.path.isfile(input_path):
            files.append(input_path)
        elif os.path.isdir(input_path):
            # Look for evaluation files in directory structure
            for root, dirs, filenames in os.walk(input_path):
                for filename in filenames:
                    if filename.endswith('_evaluation.ndjson'):
                        files.append(os.path.join(root, filename))
    else:
        # Auto-discover evaluation files in Output directory
        output_dir = Path('Output')
        if output_dir.exists():
            files.extend(list(output_dir.glob('**/*_evaluation.ndjson')))
        
        # Also check current directory for standalone evaluation files
        files.extend(list(Path('.').glob('*_evaluation.ndjson')))
    
    return sorted([str(f) for f in files])


def get_metrics_output_path(evaluation_file: str) -> str:
    """Get the output path for metrics file based on evaluation file."""
    eval_path = Path(evaluation_file)
    base_name = eval_path.stem.replace('_evaluation', '')
    return str(eval_path.parent / f"{base_name}_metrics.json")


def get_results_file_path(evaluation_file: str) -> str:
    """Get the corresponding results file path for an evaluation file."""
    eval_path = Path(evaluation_file)
    base_name = eval_path.stem.replace('_evaluation', '')
    return str(eval_path.parent / f"{base_name}_results.ndjson")


def process_evaluation_file(evaluation_file: str):
    """Process a single evaluation file and generate metrics."""
    print(f"\nProcessing: {Path(evaluation_file).name}")
    
    # Load evaluation results
    evaluation_results = load_evaluation_results(evaluation_file)
    
    if not evaluation_results:
        print("  ⚠️  No evaluation results found in file")
        return
    
    print(f"  Loaded {len(evaluation_results)} evaluation results")
    
    # Try to load corresponding results file for category metadata
    results_file = get_results_file_path(evaluation_file)
    processing_outputs = load_processing_outputs_from_results(results_file)
    
    if not processing_outputs:
        print("  ⚠️  Warning: Could not load results file for category metadata")
        print("  ℹ️  Metrics will only include overall statistics (no category breakdown)")
        # Create minimal processing outputs from evaluation results
        processing_outputs = [
            {
                'id': result.id,
                'query': '',
                'gold': result.criteria
            }
            for result in evaluation_results
        ]
    
    # Calculate categorized metrics
    metrics = calculate_categorized_accuracy_metrics(evaluation_results, processing_outputs)
    
    # Print report
    print_accuracy_report(metrics)
    
    # Save metrics
    metrics_file = get_metrics_output_path(evaluation_file)
    save_categorized_metrics(metrics, metrics_file)
    print(f"  ✅ Metrics saved to: {metrics_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate metrics JSON files from existing evaluation NDJSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script regenerates *_metrics.json files from *_evaluation.ndjson files.
Works with both organized Output directory structure and standalone files.

Examples:
  # Auto-discover and process all evaluation files in Output directory
  python generate_metrics_from_evaluation.py
  
  # Process specific evaluation file
  python generate_metrics_from_evaluation.py --input Output/Word_0905/Word_0905_evaluation.ndjson
  
  # Process all evaluation files in a directory
  python generate_metrics_from_evaluation.py --input Output
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        help='Path to evaluation NDJSON file or directory containing evaluation files (auto-discovers if not specified)'
    )
    
    args = parser.parse_args()
    
    # Find evaluation files to process
    evaluation_files = find_evaluation_files(args.input)
    
    if not evaluation_files:
        print("❌ No evaluation files found!")
        if args.input:
            print(f"   Searched in: {args.input}")
        else:
            print("   Searched in: Output/ directory and current directory")
        print("\n💡 Make sure you have evaluation files (ending with _evaluation.ndjson)")
        return
    
    print(f"📊 Found {len(evaluation_files)} evaluation file(s) to process:")
    for file in evaluation_files:
        print(f"   - {file}")
    
    print(f"\n{'='*60}")
    
    # Process each evaluation file
    for i, evaluation_file in enumerate(evaluation_files, 1):
        print(f"\n[{i}/{len(evaluation_files)}] Processing: {Path(evaluation_file).name}")
        
        try:
            process_evaluation_file(evaluation_file)
            
        except Exception as e:
            print(f"  ❌ Failed to process {Path(evaluation_file).name}: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}")
    print(f"✅ Completed processing {len(evaluation_files)} file(s)")


if __name__ == "__main__":
    main()
