#!/usr/bin/env python3
"""
Visualize benchmark comparison results.
Creates multiple charts showing precision, recall, and F1 scores.
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import sys


def load_comparison_data(json_path):
    """Load comparison data from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_metrics(comparison_data):
    """Extract case numbers and metrics from comparison data."""
    cases = []
    precisions = []
    recalls = []
    f1_scores = []

    # Check if data has a 'cases' key (new format) or is directly the cases dict (old format)
    cases_data = comparison_data.get('cases', comparison_data)

    for case_num, case_data in cases_data.items():
        # Skip non-case entries (summary, benchmark_file, etc.)
        if not case_num.isdigit():
            continue

        cases.append(int(case_num))
        precisions.append(case_data['precision'])
        recalls.append(case_data['recall'])
        f1_scores.append(case_data['f1_score'])

    # Sort by case number
    sorted_indices = np.argsort(cases)
    cases = [cases[i] for i in sorted_indices]
    precisions = [precisions[i] for i in sorted_indices]
    recalls = [recalls[i] for i in sorted_indices]
    f1_scores = [f1_scores[i] for i in sorted_indices]

    return cases, precisions, recalls, f1_scores


def create_combined_bar_chart(cases, precisions, recalls, f1_scores, output_path, title_suffix="", highlight_outliers=None):
    """Create a combined bar chart showing all metrics."""
    fig, ax = plt.subplots(figsize=(20, 8))

    x = np.arange(len(cases))
    width = 0.25

    # Create colors array - highlight outliers in red
    precision_colors = [
        'red' if highlight_outliers and c in highlight_outliers else 'steelblue' for c in cases]
    recall_colors = [
        'red' if highlight_outliers and c in highlight_outliers else 'lightcoral' for c in cases]
    f1_colors = [
        'red' if highlight_outliers and c in highlight_outliers else 'seagreen' for c in cases]

    bars1 = ax.bar(x - width, precisions, width,
                   label='Precision', color=precision_colors, alpha=0.8)
    bars2 = ax.bar(x, recalls, width, label='Recall',
                   color=recall_colors, alpha=0.8)
    bars3 = ax.bar(x + width, f1_scores, width,
                   label='F1 Score', color=f1_colors, alpha=0.8)

    ax.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('Score', fontsize=12, fontweight='bold')
    ax.set_title(f'Benchmark Results: Precision, Recall, and F1 Score by Case{title_suffix}',
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'C{c}' for c in cases], rotation=45, ha='right')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(0, 1.1)

    # Add average line
    avg_f1 = np.mean(f1_scores)
    ax.axhline(y=avg_f1, color='darkgreen', linestyle='--', linewidth=2,
               label=f'Avg F1: {avg_f1:.3f}', alpha=0.7)
    ax.legend(fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_f1_line_chart(cases, f1_scores, output_path, title_suffix="", highlight_outliers=None):
    """Create a line chart showing F1 scores."""
    fig, ax = plt.subplots(figsize=(16, 6))

    # Create colors for points
    colors = [
        'red' if highlight_outliers and c in highlight_outliers else 'steelblue' for c in cases]
    sizes = [
        200 if highlight_outliers and c in highlight_outliers else 50 for c in cases]

    ax.plot(cases, f1_scores, 'o-', linewidth=2,
            markersize=8, color='steelblue', alpha=0.6)
    ax.scatter(cases, f1_scores, c=colors, s=sizes, zorder=5,
               edgecolors='black', linewidths=1.5, alpha=0.8)

    # Annotate outliers
    if highlight_outliers:
        for i, (c, f1) in enumerate(zip(cases, f1_scores)):
            if c in highlight_outliers:
                ax.annotate(f'Case {c}\n(F1={f1:.3f})',
                            xy=(c, f1), xytext=(10, -20),
                            textcoords='offset points', fontsize=10,
                            bbox=dict(boxstyle='round,pad=0.5',
                                      fc='yellow', alpha=0.7),
                            arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))

    ax.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('F1 Score', fontsize=12, fontweight='bold')
    ax.set_title(
        f'F1 Score Progression Across Test Cases{title_suffix}', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_ylim(-0.05, 1.1)

    # Add average line
    avg_f1 = np.mean(f1_scores)
    ax.axhline(y=avg_f1, color='green', linestyle='--', linewidth=2,
               label=f'Average F1: {avg_f1:.3f}', alpha=0.7)
    ax.legend(fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_metrics_distribution(cases, precisions, recalls, f1_scores, output_path, title_suffix=""):
    """Create box plot showing distribution of metrics."""
    fig, ax = plt.subplots(figsize=(10, 6))

    data = [precisions, recalls, f1_scores]
    labels = ['Precision', 'Recall', 'F1 Score']
    colors = ['steelblue', 'lightcoral', 'seagreen']

    bp = ax.boxplot(data, labels=labels, patch_artist=True,
                    showmeans=True, meanline=True,
                    boxprops=dict(facecolor='lightblue', alpha=0.7),
                    medianprops=dict(color='red', linewidth=2),
                    meanprops=dict(color='blue', linewidth=2, linestyle='--'))

    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax.set_ylabel('Score', fontsize=12, fontweight='bold')
    ax.set_title(
        f'Distribution of Metrics{title_suffix}', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.set_ylim(0, 1.1)

    # Add statistics text
    stats_text = f"Precision: μ={np.mean(precisions):.3f}, σ={np.std(precisions):.3f}\n"
    stats_text += f"Recall: μ={np.mean(recalls):.3f}, σ={np.std(recalls):.3f}\n"
    stats_text += f"F1 Score: μ={np.mean(f1_scores):.3f}, σ={np.std(f1_scores):.3f}"
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_heatmap(cases, precisions, recalls, f1_scores, output_path, title_suffix=""):
    """Create a heatmap showing all metrics."""
    fig, ax = plt.subplots(figsize=(20, 4))

    # Prepare data matrix
    data = np.array([precisions, recalls, f1_scores])

    im = ax.imshow(data, aspect='auto', cmap='RdYlGn', vmin=0, vmax=1)

    # Set ticks
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(['Precision', 'Recall', 'F1 Score'])
    ax.set_xticks(np.arange(len(cases)))
    ax.set_xticklabels([f'C{c}' for c in cases], rotation=45, ha='right')

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Score', rotation=270, labelpad=20)

    # Add text annotations
    for i in range(3):
        for j in range(len(cases)):
            text = ax.text(j, i, f'{data[i, j]:.2f}',
                           ha="center", va="center", color="black", fontsize=7)

    ax.set_title(
        f'Performance Heatmap: All Cases{title_suffix}', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def main():
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python visualize_results.py <comparison_json_file>")
        print("Example: python visualize_results.py comparison_all_cases_benchmark_vertica_20251206_233016.json")
        sys.exit(1)

    # Paths
    base_dir = Path(__file__).parent
    comparison_file = Path(sys.argv[1])

    # If relative path provided, make it relative to base_dir
    if not comparison_file.is_absolute():
        comparison_file = base_dir / comparison_file

    # Load comparison file
    print("Loading comparison data...")
    data = load_comparison_data(comparison_file)

    # Extract metrics
    all_cases, all_precisions, all_recalls, all_f1_scores = extract_metrics(data)

    print(f"Total cases: {len(all_cases)}")
    print(f"Cases: {all_cases}")

    # Create output directory
    output_dir = base_dir / "visualizations"
    output_dir.mkdir(exist_ok=True)

    # Create visualizations
    print("\nCreating visualizations...")
    create_combined_bar_chart(
        all_cases, all_precisions, all_recalls, all_f1_scores,
        output_dir / "01_combined_metrics_all_cases.png"
    )

    create_f1_line_chart(
        all_cases, all_f1_scores,
        output_dir / "02_f1_progression.png"
    )

    create_metrics_distribution(
        all_cases, all_precisions, all_recalls, all_f1_scores,
        output_dir / "03_metrics_distribution.png"
    )

    create_heatmap(
        all_cases, all_precisions, all_recalls, all_f1_scores,
        output_dir / "04_performance_heatmap.png"
    )

    # Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"\nAll Cases ({len(all_cases)} cases):")
    print(
        f"  Average Precision: {np.mean(all_precisions):.4f} (±{np.std(all_precisions):.4f})")
    print(
        f"  Average Recall:    {np.mean(all_recalls):.4f} (±{np.std(all_recalls):.4f})")
    print(
        f"  Average F1 Score:  {np.mean(all_f1_scores):.4f} (±{np.std(all_f1_scores):.4f})")

    print("\n" + "="*80)
    print(f"All visualizations saved to: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    main()
