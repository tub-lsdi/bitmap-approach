#!/usr/bin/env python3
"""
Visualize benchmark timing results.
Creates charts showing execution times, performance trends, and comparisons.
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import sys


def load_benchmark_data(json_path):
    """Load benchmark data from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_timing_data(benchmark_data):
    """Extract case numbers and timing information."""
    cases = []
    durations = []

    for result in benchmark_data.get('results', []):
        if result.get('success', False):
            cases.append(result['case_number'])
            durations.append(result['duration_seconds'])

    # Sort by case number
    sorted_indices = np.argsort(cases)
    cases = [cases[i] for i in sorted_indices]
    durations = [durations[i] for i in sorted_indices]

    return cases, durations


def create_timing_bar_chart(cases, durations, output_path, title_suffix="", highlight_cases=None):
    """Create a bar chart showing execution times."""
    fig, ax = plt.subplots(figsize=(20, 8))

    x = np.arange(len(cases))

    # Create colors - highlight specific cases if needed
    colors = [
        'red' if highlight_cases and c in highlight_cases else 'steelblue' for c in cases]

    bars = ax.bar(x, durations, color=colors, alpha=0.7,
                  edgecolor='black', linewidth=0.5)

    # Add value labels on bars
    for i, (bar, duration) in enumerate(zip(bars, durations)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{duration:.1f}s',
                ha='center', va='bottom', fontsize=7, rotation=0)

    ax.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_title(
        f'Execution Time by Case{title_suffix}', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'C{c}' for c in cases], rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Add average line
    avg_duration = np.mean(durations)
    ax.axhline(y=avg_duration, color='red', linestyle='--', linewidth=2,
               label=f'Average: {avg_duration:.1f}s', alpha=0.7)

    # Add median line
    median_duration = np.median(durations)
    ax.axhline(y=median_duration, color='green', linestyle='--', linewidth=2,
               label=f'Median: {median_duration:.1f}s', alpha=0.7)

    ax.legend(fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_timing_distribution(durations, output_path, title_suffix=""):
    """Create histogram showing distribution of execution times."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Histogram
    ax1.hist(durations, bins=20, color='steelblue',
             alpha=0.7, edgecolor='black')
    ax1.axvline(np.mean(durations), color='red', linestyle='--',
                linewidth=2, label=f'Mean: {np.mean(durations):.1f}s')
    ax1.axvline(np.median(durations), color='green', linestyle='--',
                linewidth=2, label=f'Median: {np.median(durations):.1f}s')
    ax1.set_xlabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Frequency', fontsize=12, fontweight='bold')
    ax1.set_title(
        f'Distribution of Execution Times{title_suffix}', fontsize=13, fontweight='bold')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3, linestyle='--')

    # Box plot
    bp = ax2.boxplot([durations], vert=True, patch_artist=True,
                     showmeans=True, meanline=True,
                     boxprops=dict(facecolor='steelblue', alpha=0.7),
                     medianprops=dict(color='red', linewidth=2),
                     meanprops=dict(color='blue', linewidth=2, linestyle='--'))

    ax2.set_ylabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax2.set_title(
        f'Execution Time Statistics{title_suffix}', fontsize=13, fontweight='bold')
    ax2.set_xticklabels(['All Cases'])
    ax2.grid(axis='y', alpha=0.3, linestyle='--')

    # Add statistics text
    stats_text = f"Min: {np.min(durations):.1f}s\n"
    stats_text += f"Q1: {np.percentile(durations, 25):.1f}s\n"
    stats_text += f"Median: {np.median(durations):.1f}s\n"
    stats_text += f"Q3: {np.percentile(durations, 75):.1f}s\n"
    stats_text += f"Max: {np.max(durations):.1f}s\n"
    stats_text += f"Mean: {np.mean(durations):.1f}s\n"
    stats_text += f"Std Dev: {np.std(durations):.1f}s"
    ax2.text(1.15, 0.5, stats_text, transform=ax2.transAxes, fontsize=10,
             verticalalignment='center', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_cumulative_time_chart(cases, durations, output_path, title_suffix=""):
    """Create a chart showing cumulative execution time."""
    fig, ax = plt.subplots(figsize=(16, 6))

    cumulative = np.cumsum(durations)

    ax.plot(cases, cumulative, 'o-', linewidth=2,
            markersize=6, color='steelblue', alpha=0.7)
    ax.fill_between(cases, cumulative, alpha=0.3, color='steelblue')

    ax.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('Cumulative Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_title(
        f'Cumulative Execution Time{title_suffix}', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add total time annotation
    total_time = cumulative[-1]
    total_hours = total_time / 3600
    ax.text(0.98, 0.95, f'Total: {total_time:.1f}s ({total_hours:.2f}h)',
            transform=ax.transAxes, fontsize=12, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_comparison_chart(data1_label, cases1, durations1, data2_label, cases2, durations2, output_path):
    """Create a comparison chart between two benchmark runs."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 6))

    # Bar chart comparison (side by side for common cases)
    common_cases = sorted(set(cases1) & set(cases2))
    durations1_common = [durations1[cases1.index(c)] for c in common_cases]
    durations2_common = [durations2[cases2.index(c)] for c in common_cases]

    x = np.arange(len(common_cases))
    width = 0.35

    bars1 = ax1.bar(x - width/2, durations1_common, width, label=data1_label,
                    color='steelblue', alpha=0.7, edgecolor='black', linewidth=0.5)
    bars2 = ax1.bar(x + width/2, durations2_common, width, label=data2_label,
                    color='coral', alpha=0.7, edgecolor='black', linewidth=0.5)

    ax1.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax1.set_title('Execution Time Comparison by Case',
                  fontsize=13, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels([f'C{c}' for c in common_cases],
                        rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3, linestyle='--')

    # Box plot comparison
    bp = ax2.boxplot([durations1, durations2], labels=[data1_label, data2_label],
                     patch_artist=True, showmeans=True, meanline=True,
                     boxprops=dict(alpha=0.7),
                     medianprops=dict(color='red', linewidth=2),
                     meanprops=dict(color='blue', linewidth=2, linestyle='--'))

    colors = ['steelblue', 'coral']
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)

    ax2.set_ylabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax2.set_title('Execution Time Distribution Comparison',
                  fontsize=13, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3, linestyle='--')

    # Add statistics
    stats_text = f"{data1_label}:\n  Mean: {np.mean(durations1):.1f}s\n  Median: {np.median(durations1):.1f}s\n\n"
    stats_text += f"{data2_label}:\n  Mean: {np.mean(durations2):.1f}s\n  Median: {np.median(durations2):.1f}s"
    ax2.text(1.15, 0.5, stats_text, transform=ax2.transAxes, fontsize=10,
             verticalalignment='center', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_timing_vs_accuracy_chart(cases, durations, f1_scores, output_path, title_suffix=""):
    """Create a scatter plot showing timing vs accuracy tradeoff."""
    fig, ax = plt.subplots(figsize=(12, 8))

    # Color points by F1 score
    scatter = ax.scatter(durations, f1_scores, c=f1_scores, s=100, cmap='RdYlGn',
                         vmin=0, vmax=1, alpha=0.7, edgecolors='black', linewidth=1)

    # Add case labels
    for case, dur, f1 in zip(cases, durations, f1_scores):
        ax.annotate(f'C{case}', (dur, f1), fontsize=8,
                    ha='center', va='center')

    ax.set_xlabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_ylabel('F1 Score', fontsize=12, fontweight='bold')
    ax.set_title(
        f'Execution Time vs F1 Score{title_suffix}', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_ylim(-0.05, 1.1)

    # Add colorbar
    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label('F1 Score', rotation=270, labelpad=20)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def main():
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python visualize_timing.py <benchmark_json_file>")
        print("Example: python visualize_timing.py benchmark_vertica_20251206_233016.json")
        sys.exit(1)

    # Paths
    base_dir = Path(__file__).parent
    benchmark_file = Path(sys.argv[1])

    # If relative path provided, make it relative to base_dir
    if not benchmark_file.is_absolute():
        benchmark_file = base_dir / benchmark_file

    # Derive comparison file from benchmark file
    comparison_file = benchmark_file.parent / f"comparison_all_cases_{benchmark_file.stem}.json"

    # Load benchmark data
    print("Loading benchmark timing data...")
    data = load_benchmark_data(benchmark_file)

    # Extract timing data
    all_cases, all_durations = extract_timing_data(data)

    print(f"Total cases with timing: {len(all_cases)}")
    print(f"Cases: {all_cases}")

    # Load comparison data for F1 scores
    print("\nLoading F1 score data...")
    with open(comparison_file, 'r') as f:
        comp_data = json.load(f)

    # Extract F1 scores
    cases_comp = []
    f1_scores = []
    for case_num, case_data in comp_data.get('cases', comp_data).items():
        if case_num.isdigit():
            cases_comp.append(int(case_num))
            f1_scores.append(case_data['f1_score'])

    all_f1_cases = cases_comp
    all_f1_scores = f1_scores

    # Create output directory
    output_dir = base_dir / "visualizations"
    output_dir.mkdir(exist_ok=True)

    # Create timing visualizations
    print("\nCreating timing visualizations...")

    create_timing_bar_chart(
        all_cases, all_durations,
        output_dir / "09_execution_time_by_case.png",
        title_suffix=" - All Cases"
    )

    create_timing_distribution(
        all_durations,
        output_dir / "10_execution_time_distribution.png",
        title_suffix=" - All Cases"
    )

    create_cumulative_time_chart(
        all_cases, all_durations,
        output_dir / "11_cumulative_execution_time.png",
        title_suffix=" - All Cases"
    )

    # Timing vs Accuracy
    create_timing_vs_accuracy_chart(
        all_cases, all_durations, all_f1_scores,
        output_dir / "13_timing_vs_accuracy.png",
        title_suffix=" - All Cases"
    )

    # Print summary statistics
    print("\n" + "="*80)
    print("TIMING SUMMARY STATISTICS")
    print("="*80)

    print(f"\nAll Cases ({len(all_cases)} cases):")
    print(
        f"  Total Time: {np.sum(all_durations):.1f}s ({np.sum(all_durations)/3600:.2f}h)")
    print(
        f"  Average Time: {np.mean(all_durations):.1f}s (±{np.std(all_durations):.1f}s)")
    print(f"  Median Time: {np.median(all_durations):.1f}s")
    print(
        f"  Min Time: {np.min(all_durations):.1f}s (Case {all_cases[np.argmin(all_durations)]})")
    print(
        f"  Max Time: {np.max(all_durations):.1f}s (Case {all_cases[np.argmax(all_durations)]})")

    # Top 5 slowest cases
    slowest_indices = np.argsort(all_durations)[-5:][::-1]
    print("\nTop 5 Slowest Cases:")
    for idx in slowest_indices:
        case = all_cases[idx]
        duration = all_durations[idx]
        f1_idx = all_f1_cases.index(case)
        f1 = all_f1_scores[f1_idx]
        print(f"  Case {case}: {duration:.1f}s (F1: {f1:.3f})")

    # Top 5 fastest cases
    fastest_indices = np.argsort(all_durations)[:5]
    print("\nTop 5 Fastest Cases:")
    for idx in fastest_indices:
        case = all_cases[idx]
        duration = all_durations[idx]
        f1_idx = all_f1_cases.index(case)
        f1 = all_f1_scores[f1_idx]
        print(f"  Case {case}: {duration:.1f}s (F1: {f1:.3f})")

    print("\n" + "="*80)
    print(f"All timing visualizations saved to: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    main()
