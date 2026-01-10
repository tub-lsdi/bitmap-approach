import argparse
import json
import os
import sys
import polars as pl
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Tuple, Set

def load_groundtruth(filepath: str) -> Set[Tuple[str, str]]:
    mappings = set()
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    # Lowercase for comparison
                    mappings.add((parts[0].lower().strip(), parts[1].lower().strip()))
    except FileNotFoundError:
        print(f"Error: Groundtruth file {filepath} not found.", file=sys.stderr)
    return mappings

def load_results(filepath: str) -> List[Dict]:
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return data.get('results', [])
    except FileNotFoundError:
        print(f"Error: Result file {filepath} not found.", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from {filepath}.", file=sys.stderr)
        return []

def evaluate_case(groundtruth: Set[Tuple[str, str]], results: List[Dict]) -> Dict:
    result_mappings = set()
    for m in results:
        if 'r_val' in m and 's_val' in m:
             result_mappings.add((m['r_val'].lower().strip(), m['s_val'].lower().strip()))
    
    tp = len(groundtruth.intersection(result_mappings))
    fp = len(result_mappings - groundtruth)
    fn = len(groundtruth - result_mappings)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn
    }

def process_file(file_path: str, groundtruth_dir: str) -> pl.DataFrame:
    results_data = load_results(file_path)
    filename = os.path.basename(file_path)
    
    eval_data = []
    
    for case in results_data:
        case_num = case['case_number']
        gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")
        
        if not os.path.exists(gt_file):
            # Try alternative naming if needed, or just warn
            print(f"Warning: Groundtruth file {gt_file} not found for case {case_num}.")
            continue
            
        gt_mappings = load_groundtruth(gt_file)
        if not gt_mappings:
             print(f"Warning: No mappings found in groundtruth for case {case_num}.")
             
        metrics = evaluate_case(gt_mappings, case.get('output', {}).get('mappings', []))
        
        metrics['case'] = case_num
        metrics['file'] = filename
        metrics['duration'] = case.get('duration_seconds', 0.0)
        eval_data.append(metrics)
        
    if not eval_data:
        return pl.DataFrame()
        
    return pl.DataFrame(eval_data)

def plot_single_file(df: pl.DataFrame, output_file: str = None):
    if df.is_empty():
        print("No data to plot.")
        return

    # Plot F1 score per case
    plt.figure(figsize=(14, 6))
    sns.barplot(data=df.to_pandas(), x='case', y='f1')
    plt.title(f"F1 Score per Case - {df['file'][0]}")
    plt.xlabel("Case Number")
    plt.ylabel("F1 Score")
    plt.xticks(rotation=45)
    plt.ylim(0, 1.05)
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file)
        print(f"Plot saved to {output_file}")
    else:
        plt.show()

def plot_comparison(dfs: List[pl.DataFrame], output_file: str = None):
    if not dfs:
        print("No data to compare.")
        return
        
    combined_df = pl.concat(dfs)
    if combined_df.is_empty():
        print("Combined data is empty.")
        return

    plt.figure(figsize=(16, 8))
    sns.barplot(data=combined_df.to_pandas(), x='case', y='f1', hue='file')
    plt.title("F1 Score Comparison per Case")
    plt.xlabel("Case Number")
    plt.ylabel("F1 Score")
    plt.xticks(rotation=45)
    plt.ylim(0, 1.05)
    plt.legend(title='File', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file)
        print(f"Comparison plot saved to {output_file}")
    else:
        plt.show()

def main():
    parser = argparse.ArgumentParser(description="Evaluate benchmark results.")
    parser.add_argument("--groundtruth_dir", default="benchmark-data", help="Directory containing groundtruth files")
    parser.add_argument("--results_dir", default="eval-result-data/duckdb_git_tables_bench", help="Directory containing result files")
    parser.add_argument("--files", nargs='+', help="Specific result files to evaluate (filenames in results_dir)")
    parser.add_argument("--plot", action="store_true", help="Generate plots")
    parser.add_argument("--output", help="Output file for plot (e.g., plot.png)")
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    
    args = parser.parse_args()
    
    groundtruth_dir = args.groundtruth_dir
    results_dir = args.results_dir

    if not os.path.exists(groundtruth_dir):
        print(f"Error: Groundtruth directory {groundtruth_dir} does not exist.")
        return

    if not os.path.exists(results_dir):
        print(f"Error: Results directory {results_dir} does not exist.")
        return

    files_to_process = []
    if args.files:
        for f in args.files:
            files_to_process.append(os.path.join(results_dir, f))
    else:
        # If no files specified, list all json files in results_dir
        for f in os.listdir(results_dir):
            if f.endswith(".json"):
                files_to_process.append(os.path.join(results_dir, f))
    
    if not files_to_process:
        print("No files to process.")
        return

    dfs = []
    for file_path in files_to_process:
        print(f"Processing {file_path}...")
        df = process_file(file_path, groundtruth_dir)
        if not df.is_empty():
            dfs.append(df)
            if args.summary:
                print(f"Summary for {os.path.basename(file_path)}:")
                print(df.select([
                    pl.col("precision").mean().alias("mean_precision"),
                    pl.col("recall").mean().alias("mean_recall"),
                    pl.col("f1").mean().alias("mean_f1"),
                    pl.col("duration").mean().alias("mean_duration")
                ]))
                print("-" * 40)

    if args.plot and dfs:
        if len(dfs) == 1:
            plot_single_file(dfs[0], args.output)
        else:
            plot_comparison(dfs, args.output)

if __name__ == "__main__":
    main()
