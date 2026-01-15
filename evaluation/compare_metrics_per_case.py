import argparse
import json
import os
import sys
import re
import polars as pl
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Tuple, Set
import matplotlib.ticker as ticker
from matplotlib.gridspec import GridSpec

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import load_results, load_groundtruth, calculate_case_metrics


def process_file(file_path: str, groundtruth_dir: str) -> pl.DataFrame:
    results_data = load_results(file_path)
    filename = os.path.basename(file_path)
    
    # Clean filename: remove benchmark_ prefix, extension, and trailing timestamp
    if filename.startswith("benchmark_"):
        filename = filename[len("benchmark_"):]
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'_\d{8}_\d{6}$', '', filename)
    
    eval_data = []
    
    for case in results_data:
        case_num = case['case_number']
        gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")
        
        if not os.path.exists(gt_file):
            print(f"Warning: Groundtruth file {gt_file} not found for case {case_num}.")
            continue
            
        gt_mappings = load_groundtruth(gt_file)
        if not gt_mappings:
             print(f"Warning: No mappings found in groundtruth for case {case_num}.")
             
        metrics = calculate_case_metrics(gt_mappings, case.get('output', {}).get('mappings', []))
        
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

def plot_bar_comparison(dfs: List[pl.DataFrame], output_file: str = None, show_table: bool = True):
    if not dfs:
        print("No data to compare.")
        return
        
    combined_df = pl.concat(dfs)
    if combined_df.is_empty():
        print("Combined data is empty.")
        return

    # Calculate summary stats
    summary_df = combined_df.group_by("file", maintain_order=True).agg([
        pl.col("precision").mean().alias("Precision"),
        pl.col("recall").mean().alias("Recall"),
        pl.col("f1").mean().alias("F1"),
        pl.col("duration").median().alias("Duration (s)")
    ])
    
    # Predefined colors
    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
        "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5"
    ]
    
    unique_files = summary_df['file'].to_list()
    file_colors = {f: colors[i % len(colors)] for i, f in enumerate(unique_files)}

    # Convert to pandas for plotting
    plot_data = combined_df.to_pandas()
    summary_data = summary_df.to_pandas()
    
    cell_text = []
    row_colors = []
    
    for _, row in summary_data.iterrows():
        filename = row['file']
        r = [""]
        r.append(f"{row['Precision']:.3f}")
        r.append(f"{row['Recall']:.3f}")
        r.append(f"{row['F1']:.3f}")
        r.append(f"{row['Duration (s)']:.2f}")
        cell_text.append(r)
        row_colors.append(file_colors[filename])

    col_labels = ["File", "Precision", "Recall", "F1", "Duration (s)"]

    fig_width = 20 if show_table else 14
    fig, ax = plt.subplots(figsize=(fig_width, 8))
    
    sns.barplot(data=plot_data, x='case', y='f1', hue='file', ax=ax, palette=file_colors)
    ax.set_title("F1 Score Comparison per Case")
    ax.set_xlabel("Case Number")
    ax.set_ylabel("F1 Score")
    
    ax.xaxis.set_major_locator(ticker.FixedLocator(ax.get_xticks()))
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
    
    ax.set_ylim(0, 1.05)
    
    legend = ax.legend(title='File', bbox_to_anchor=(1.01, 1), loc='upper left')
    
    if show_table:
        plt.subplots_adjust(right=0.65)
        
        table = plt.table(cellText=cell_text,
                          colLabels=col_labels,
                          loc='right',
                          bbox=[1.02, 0.4, 0.45, 0.3])
        
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        for i, color in enumerate(row_colors):
            cell = table[i + 1, 0]
            cell.set_facecolor(color)
    else:
        plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, bbox_inches='tight')
        print(f"Comparison plot saved to {output_file}")
    else:
        plt.show()

def plot_heatmap(dfs: List[pl.DataFrame], output_file: str = None, show_table: bool = True):
    if not dfs:
        print("No data to plot.")
        return
        
    combined_df = pl.concat(dfs)
    if combined_df.is_empty():
        print("Combined data is empty.")
        return

    # Calculate summary stats for table
    summary_df = combined_df.group_by("file", maintain_order=True).agg([
        pl.col("precision").mean().alias("Precision"),
        pl.col("recall").mean().alias("Recall"),
        pl.col("f1").mean().alias("F1"),
        pl.col("duration").median().alias("Duration (s)")
    ])
    
    summary_data = summary_df.to_pandas()
    cell_text = []
    
    for _, row in summary_data.iterrows():
        r = [row['file']]
        r.append(f"{row['Precision']:.3f}")
        r.append(f"{row['Recall']:.3f}")
        r.append(f"{row['F1']:.3f}")
        duration = row.get('Duration (s)', 0.0)
        try:
            if duration is None or duration != duration:
                duration = 0.0
        except Exception:
            duration = 0.0
        r.append(f"{float(duration):.2f}")
        cell_text.append(r)
        
    col_labels = ["File", "Precision", "Recall", "F1", "Duration (s)"]

    try:
        pivot_df = combined_df.pivot(values="f1", index="file", on="case", aggregate_function="first")
    except TypeError:
        pivot_df = combined_df.pivot(values="f1", index="file", columns="case", aggregate_function="first")
        
    pandas_df = pivot_df.to_pandas()
    pandas_df.set_index("file", inplace=True)
    
    try:
        sorted_cols = sorted(pandas_df.columns, key=lambda x: int(x))
    except:
        sorted_cols = sorted(pandas_df.columns)
    pandas_df = pandas_df.reindex(sorted_cols, axis=1)
    
    # Figure layout
    fig_height = max(3, len(dfs) * 0.4 + 1.5)
    
    if show_table:
        fig = plt.figure(figsize=(24, fig_height))
        gs = GridSpec(1, 2, width_ratios=[4, 2], figure=fig)
        ax_heatmap = fig.add_subplot(gs[0])
        ax_table = fig.add_subplot(gs[1])
        ax_table.axis('off')
    else:
        fig = plt.figure(figsize=(16, fig_height))
        ax_heatmap = fig.add_subplot(111)
    
    sns.heatmap(pandas_df, annot=False, cmap="RdYlGn", fmt=".2f",
                cbar_kws={'label': 'F1 Score', 'shrink': 0.5}, ax=ax_heatmap, vmin=0, vmax=1, square=True)
    
    ax_heatmap.set_title("F1 Score Heatmap per Case")
    ax_heatmap.set_xlabel("Case Number")
    ax_heatmap.set_ylabel("File")
    
    if show_table:
        # Table
        col_widths = [0.4, 0.15, 0.15, 0.15, 0.15]
        
        table = ax_table.table(cellText=cell_text,
                               colLabels=col_labels,
                               colWidths=col_widths,
                               loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, bbox_inches='tight')
        print(f"Heatmap saved to {output_file}")
    else:
        plt.show()

def main():
    parser = argparse.ArgumentParser(description="Evaluate benchmark results.")
    parser.add_argument("--groundtruth_dir", default="benchmark-data", help="Directory containing groundtruth files")
    parser.add_argument("--results_dir", default="", help="Directory containing result files")
    parser.add_argument("--files", nargs='+', help="Specific result files to evaluate (filenames in results_dir)")
    parser.add_argument("--plot", nargs='?', const='bar', default=None, help="Generate plots. Options: 'bar' (default), 'heatmap'")
    parser.add_argument("--output", help="Output file for plot (e.g., plot.png)")
    parser.add_argument("--summary", action="store_true", help="Print summary statistics")
    parser.add_argument("--no-table", action="store_true", help="Do not show the summary table in the plot")
    
    args = parser.parse_args()
    
    groundtruth_dir = args.groundtruth_dir
    results_dir = args.results_dir if args.results_dir and args.results_dir != "" else os.curdir

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
                    pl.col("duration").median().alias("mean_duration")
                ]))
                print("-" * 40)

    if args.plot and dfs:
        show_table = not args.no_table
        if args.plot == 'heatmap':
            plot_heatmap(dfs, args.output, show_table)
        else:
            if len(dfs) == 1:
                plot_single_file(dfs[0], args.output)
            else:
                plot_bar_comparison(dfs, args.output, show_table)

if __name__ == "__main__":
    main()
