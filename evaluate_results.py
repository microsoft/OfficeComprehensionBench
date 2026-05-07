#!/usr/bin/env python3
"""
Standalone evaluation script for processing outputs already generated.

"""

import asyncio
import argparse
import json
import os
from pathlib import Path
from typing import List, Dict, Any
import glob
from evaluation import (
    evaluate_batch_results_with_accuracy_prompt,
    calculate_categorized_accuracy_metrics,
    print_accuracy_report,
    save_evaluation_results,
    save_categorized_metrics
)


def find_results_files(input_path: str = None) -> list:
    """Find results files to evaluate."""
    files = []
    
    if input_path and os.path.exists(input_path):
        if os.path.isfile(input_path):
            files.append(input_path)
        elif os.path.isdir(input_path):
            # Look for results files in directory structure
            for root, dirs, filenames in os.walk(input_path):
                for filename in filenames:
                    if filename.endswith('_results.ndjson'):
                        files.append(os.path.join(root, filename))
    else:
        # Auto-discover results files in Output directory
        output_dir = Path('Output')
        if output_dir.exists():
            files.extend(list(output_dir.glob('**/*_results.ndjson')))
        
        # Also check current directory for standalone results files
        files.extend(list(Path('.').glob('*_results.ndjson')))
    
    return sorted(files)


def get_evaluation_structure(results_file: str) -> Dict[str, str]:
    """Get evaluation output structure based on results file location."""
    results_path = Path(results_file)
    
    # If it's in organized structure (Output/[name]/[name]_results.ndjson)
    if results_path.parent.name != '.' and results_path.parent.parent.name == 'Output':
        # Use organized structure
        base_name = results_path.stem.replace('_results', '')
        output_dir = results_path.parent
        
        return {
            "evaluation_file": str(output_dir / f"{base_name}_evaluation.ndjson"),
            "metrics_file": str(output_dir / f"{base_name}_metrics.json"),
            "plots_dir": str(output_dir / "plots")
        }
    else:
        # Use standalone structure
        base_name = results_path.stem.replace('_results', '')
        output_dir = results_path.parent
        
        return {
            "evaluation_file": str(output_dir / f"{base_name}_evaluation.ndjson"),
            "metrics_file": str(output_dir / f"{base_name}_metrics.json"),
            "plots_dir": str(output_dir / "plots")
        }
    """Load processing outputs from NDJSON file."""
    outputs = []
    
    with open(ndjson_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                outputs.append(data)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num}: {e}")
                continue
    
    return outputs


def load_processing_outputs(ndjson_path: str) -> List[Dict[str, Any]]:
    """Load processing outputs from NDJSON file."""
    outputs = []
    
    with open(ndjson_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                outputs.append(data)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num}: {e}")
                continue
    
    return outputs


# Import visualization functions
def load_metrics_for_visualization(file_path: str) -> dict:
    """Load categorized metrics from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_visualization_plots(metrics_file_path: str, output_base_dir: str = None):
    """Generate ranking plots from categorized metrics."""
    try:
        # Import plotting functions
        import matplotlib.pyplot as plt
        import seaborn as sns
        import pandas as pd
        import numpy as np
        import warnings
        warnings.filterwarnings('ignore')
        
        # Set style for better-looking plots
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        # Create output directory
        if output_base_dir:
            output_dir = Path(output_base_dir)
        else:
            # Default to plots directory next to metrics file
            output_dir = Path(os.path.dirname(metrics_file_path)) / 'plots'
        output_dir.mkdir(exist_ok=True)
        
        print("  Loading categorized metrics for visualization...")
        metrics = load_metrics_for_visualization(metrics_file_path)
        
        print("  Preparing data for plotting...")
        # Convert metrics to DataFrame
        data = []
        for category_type, categories in metrics['by_category'].items():
            for category_name, stats in categories.items():
                data.append({
                    'category_type': category_type,
                    'category_name': category_name,
                    'accuracy': stats['accuracy'],
                    'total_evaluated': stats['total_evaluated'],
                    'passed_evaluations': stats['passed_evaluations'],
                    'evaluation_success_rate': stats['evaluation_success_rate']
                })
        
        df = pd.DataFrame(data)
        
        if len(df) == 0:
            print("  Warning: No categorized data found for visualization")
            return
        
        print(f"  Creating ranking plots for {df['category_type'].nunique()} category types...")
        
        # Create ranking plots
        for category_type in df['category_type'].unique():
            cat_data = df[df['category_type'] == category_type].copy()
            cat_data = cat_data.sort_values('accuracy', ascending=True)
            
            fig, ax = plt.subplots(figsize=(12, max(8, len(cat_data) * 0.5)))
            
            # Create color map based on accuracy
            colors = plt.cm.RdYlGn(cat_data['accuracy'])
            
            bars = ax.barh(range(len(cat_data)), cat_data['accuracy'], color=colors)
            
            # Add value labels on bars
            for i, (bar, acc, total) in enumerate(zip(bars, cat_data['accuracy'], cat_data['total_evaluated'])):
                ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2, 
                       f'{acc:.3f} ({total})', va='center', fontsize=10)
            
            ax.set_yticks(range(len(cat_data)))
            ax.set_yticklabels(cat_data['category_name'])
            ax.set_xlabel('Accuracy')
            ax.set_title(f'Accuracy Ranking: {category_type.replace("_", " ").title()}', 
                        fontsize=14, fontweight='bold')
            ax.set_xlim(0, 1)
            ax.grid(True, alpha=0.3, axis='x')
            
            plt.tight_layout()
            plt.savefig(output_dir / f'ranking_{category_type}.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        print(f"  ✅ Ranking plots saved to: {output_dir}")
        plot_files = list(output_dir.glob('ranking_*.png'))
        for file in sorted(plot_files):
            print(f"    - {file.name}")
            
    except Exception as e:
        print(f"  ⚠️  Visualization generation failed: {str(e)}")


async def evaluate_single_file(results_file: str, max_concurrent: int = 3, generate_plots: bool = True):
    """Evaluate a single results file with organized output structure."""
    print(f"Processing: {Path(results_file).name}")
    
    # Get evaluation structure
    eval_structure = get_evaluation_structure(results_file)
    
    # Load processing outputs
    processing_outputs = load_processing_outputs(results_file)
    
    if not processing_outputs:
        print("  ⚠️  No processing outputs found in file")
        return
    
    print(f"  Loaded {len(processing_outputs)} processing outputs")
    
    # Run evaluation
    evaluation_results = await evaluate_batch_results_with_accuracy_prompt(
        processing_outputs,
        max_concurrent=max_concurrent
    )
    
    if evaluation_results:
        # Calculate and print metrics with categorization
        metrics = calculate_categorized_accuracy_metrics(evaluation_results, processing_outputs)
        print_accuracy_report(metrics)
        
        # Save evaluation results
        save_evaluation_results(evaluation_results, eval_structure["evaluation_file"])
        print(f"  Evaluation results saved to: {eval_structure['evaluation_file']}")
        
        # Save categorized metrics
        save_categorized_metrics(metrics, eval_structure["metrics_file"])
        print(f"  Categorized metrics saved to: {eval_structure['metrics_file']}")
        
        # Generate visualization plots automatically
        if generate_plots:
            print("  Generating visualization plots...")
            generate_visualization_plots(eval_structure["metrics_file"], eval_structure["plots_dir"])
        
    else:
        print("  ⚠️  No evaluations were performed (no queries with gold standards found)")


async def main():
    """Main entry point with organized structure support."""
    parser = argparse.ArgumentParser(
        description="Evaluate existing processing results against gold standards using GPT-4.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script evaluates processing outputs that already contain gold standards.
Works with both organized Output directory structure and standalone files.

Examples:
  # Auto-discover and evaluate all results files in Output directory
  python evaluate_results.py
  
  # Evaluate specific results file
  python evaluate_results.py --input Output/Word_0905/Word_0905_results.ndjson
  
  # Evaluate all results files in a directory
  python evaluate_results.py --input Output
  
  # Evaluate without generating plots
  python evaluate_results.py --input results.ndjson --no-plots
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        help='Path to results NDJSON file or directory containing results files (auto-discovers if not specified)'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=3,
        help='Maximum concurrent evaluations (default: 3)'
    )
    
    parser.add_argument(
        '--no-plots',
        action='store_true',
        help='Skip generating visualization plots'
    )
    
    args = parser.parse_args()
    
    # Find results files to process
    results_files = find_results_files(args.input)
    
    if not results_files:
        print("❌ No results files found!")
        if args.input:
            print(f"   Searched in: {args.input}")
        else:
            print("   Searched in: Output/ directory and current directory")
        print("\n💡 Make sure you have run the response processor first to generate results")
        return
    
    print(f"📊 Found {len(results_files)} results file(s) to evaluate:")
    for file in results_files:
        print(f"   - {file}")
    
    print(f"\n{'='*60}")
    
    # Process each results file
    generate_plots = not args.no_plots
    
    for i, results_file in enumerate(results_files, 1):
        print(f"Evaluating {i}/{len(results_files)}: {Path(results_file).name}")
        
        try:
            await evaluate_single_file(results_file, args.max_concurrent, generate_plots)
            
            if i < len(results_files):
                print()
                
        except Exception as e:
            print(f"  ❌ Failed to evaluate {Path(results_file).name}: {str(e)}")
            continue
    
    print(f"\n{'='*60}")
    print(f"✅ Completed evaluation for {len(results_files)} file(s)")


if __name__ == "__main__":
    asyncio.run(main())