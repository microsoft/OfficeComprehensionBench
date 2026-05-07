#!/usr/bin/env python3
"""
Categorized Metrics Ranking Visualization Script

Creates ranking visualizations for analyzing model performance across different categories.

"""

import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import argparse
import os
import warnings
warnings.filterwarnings('ignore')

# Set style for better-looking plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

def load_metrics_for_visualization(file_path: str) -> dict:
    """Load categorized metrics from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def prepare_data_for_plotting(metrics: dict) -> pd.DataFrame:
    """Convert metrics to DataFrame for easier plotting."""
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
    
    return pd.DataFrame(data)

def create_ranking_plots(df: pd.DataFrame, output_dir: Path):
    """Create horizontal bar charts ranking categories by accuracy."""
    
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

def generate_visualization_plots(metrics_file_path: str, output_base_dir: str = None):
    """Generate ranking plots from categorized metrics."""
    
    try:
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
        df = prepare_data_for_plotting(metrics)
        
        if len(df) == 0:
            print("  Warning: No categorized data found for visualization")
            return
        
        print(f"  Creating ranking plots for {df['category_type'].nunique()} category types...")
        create_ranking_plots(df, output_dir)
        
        # Generate size-based visualizations if results file exists
        results_dir = Path(metrics_file_path).parent
        results_file = results_dir / f"{results_dir.name}_results.ndjson"
        if not results_file.exists():
            # Try to find results file with different naming pattern
            possible_results = list(results_dir.glob("*_results.ndjson"))
            if possible_results:
                results_file = possible_results[0]
        
        if results_file.exists():
            print("  Generating size-based visualizations...")
            try:
                import subprocess
                import sys
                
                # Call the size visualization script
                result = subprocess.run([
                    sys.executable, "visualize_size_metrics.py", str(results_dir)
                ], capture_output=True, text=True, cwd=Path(__file__).parent)
                
                if result.returncode == 0:
                    print("  ✅ Size ranking plot generated successfully")
                else:
                    print(f"  ⚠️  Size visualization warning: {result.stderr.strip()}")
            except Exception as e:
                print(f"  ⚠️  Could not generate size plots: {str(e)}")
        
        print(f"  ✅ Ranking plots saved to: {output_dir}")
        plot_files = list(output_dir.glob('ranking_*.png'))
        for file in sorted(plot_files):
            print(f"    - {file.name}")
            
    except Exception as e:
        print(f"  ⚠️  Visualization generation failed: {str(e)}")


def find_metrics_files(input_path: str = None) -> list:
    """Find metrics files to visualize."""
    files = []
    
    if input_path and os.path.exists(input_path):
        if os.path.isfile(input_path):
            files.append(input_path)
        elif os.path.isdir(input_path):
            # Look for metrics files in directory structure
            for root, dirs, filenames in os.walk(input_path):
                for filename in filenames:
                    if filename.endswith('_metrics.json'):
                        files.append(os.path.join(root, filename))
    else:
        # Auto-discover metrics files in Output directory
        output_dir = Path('Output')
        if output_dir.exists():
            files.extend(list(output_dir.glob('**/*_metrics.json')))
        
        # Also check current directory for standalone metrics files
        files.extend(list(Path('.').glob('*_metrics.json')))
    
    return sorted(files)

def main():
    """Main function with command line argument support."""
    parser = argparse.ArgumentParser(
        description="Generate ranking visualizations from categorized metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover and visualize all metrics files in Output directory
  python visualize_categorized_metrics.py
  
  # Visualize specific metrics file
  python visualize_categorized_metrics.py --input Output/Word_0905/Word_0905_metrics.json
  
  # Visualize all metrics files in a directory
  python visualize_categorized_metrics.py --input Output
  
  # Visualize with custom output directory
  python visualize_categorized_metrics.py --input metrics.json --output custom_plots
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        help='Path to metrics JSON file or directory containing metrics files (auto-discovers if not specified)'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output directory for plots (defaults to plots/ next to metrics file or current directory)'
    )
    
    args = parser.parse_args()
    
    # Find metrics files to process
    metrics_files = find_metrics_files(args.input)
    
    if not metrics_files:
        print("❌ No metrics files found!")
        if args.input:
            print(f"   Searched in: {args.input}")
        else:
            print("   Searched in: Output/ directory and current directory")
        print("\n💡 Make sure you have run the response processor with --evaluate first")
        return
    
    print(f"📊 Found {len(metrics_files)} metrics file(s) to visualize:")
    for file in metrics_files:
        print(f"   - {file}")
    
    print(f"\n{'='*60}")
    
    # Process each metrics file
    for i, metrics_file in enumerate(metrics_files, 1):
        print(f"Processing {i}/{len(metrics_files)}: {Path(metrics_file).name}")
        
        # Determine output directory
        if args.output:
            output_dir = args.output
        else:
            # Default: plots directory next to metrics file
            output_dir = str(Path(metrics_file).parent / 'plots')
        
        # Generate visualizations
        generate_visualization_plots(metrics_file, output_dir)
        
        if i < len(metrics_files):
            print()
    
    print(f"\n{'='*60}")
    print(f"✅ Completed visualization generation for {len(metrics_files)} file(s)")


if __name__ == "__main__":
    main()